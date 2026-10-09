"""Changing and removing a transaction.

A transaction's effect on its account is undone and, for a change, applied
again in the same commit, on the ledger day the transaction belongs to. The
balance, the ledger and the row therefore never disagree.

A transaction the application wrote by itself (a debt payment, a card
payment, an asset trade) is one half of a larger record. Its amount, account
and wording are decided by that other half and stay as they are; its date can
change, and removing it undoes the other half with it: the installments go
back to the debt, the card owes again, the holding returns or leaves. One
written before these links were kept cannot be traced to its other half and
is left alone.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from database.db import (
    ASSET_PURCHASE, ASSET_SALE, CARD_PAYMENT, DEBT_PAYMENT, adjust_account_balance,
    drop_record_link, get_connection, read_record_link,
)
from services.account_service import AccountService
from services.transaction_service import SECRET_KEY
from utils.crypto import decrypt, encrypt
from utils.errors import DecryptionError
from utils.financial_decimal import decimal_from, fiat

# Categories written by the application itself; never offered in a form.
SYSTEM_CATEGORIES = ("Varlık Alımı", "Varlık Satışı", "Kredi Taksiti", "Borç Ödeme")

NOT_FOUND = "İşlem bulunamadı."
LINKED = "Bu işlem uygulama tarafından oluşturuldu ve buradan değiştirilemez."
PENDING = "Bekleyen bir işlem Borçlar ve ödemeler bölümünden değiştirilir."
UNREADABLE = "Bu kayıt okunamadığı için değiştirilemez."
FUTURE = "İşlem tarihi gelecekte olamaz."
BAD_DATE = "İşlem tarihi geçersiz."
BAD_CATEGORY = "Bu kategori bu işlem türü için kullanılamaz."
BAD_KIND = "İşlem türü geçersiz."
SOLD_SINCE = "Bu alımdaki varlığın bir kısmı ya da tamamı satıldı. Önce satışı geri alın."

PLAIN = "plain"
INSTALLMENT = "installment"
_EVERYTHING_BUT_THE_DATE = ("amount", "category", "description", "account", "kind")
# What cannot be changed on each kind of record.
FIXED = {
    PLAIN: (),
    # The plan belongs to the card it was bought on.
    INSTALLMENT: ("account", "kind"),
    DEBT_PAYMENT: _EVERYTHING_BUT_THE_DATE,
    CARD_PAYMENT: _EVERYTHING_BUT_THE_DATE,
    ASSET_PURCHASE: _EVERYTHING_BUT_THE_DATE,
    ASSET_SALE: _EVERYTHING_BUT_THE_DATE,
}

_OPPOSITE = {"income": "expense", "expense": "income"}


def _direction(kind: str) -> str:
    """Which way a record moves its account; a card payment raises the card."""
    return "expense" if kind == "expense" else "income"


def _has_installment_plan(cursor, account_id, stamp) -> bool:
    exists = cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'installment_plans'"
    ).fetchone()
    if not exists:
        return False
    return cursor.execute(
        "SELECT 1 FROM installment_plans WHERE account_id = ? AND created_at = ?",
        (account_id, stamp),
    ).fetchone() is not None


def _load(cursor, transaction_id) -> dict:
    """The row with its amount decrypted, what it is, and why it is locked."""
    row = cursor.execute(
        "SELECT id, account_id, amount, type, category, description, transaction_date,"
        " IFNULL(status, 'completed') AS status FROM transactions WHERE id = ?",
        (int(transaction_id),),
    ).fetchone()
    if row is None:
        raise ValueError(NOT_FOUND)

    amount, description, locked = None, "", ""
    try:
        amount = float(fiat(decrypt(row["amount"], SECRET_KEY)))
        description = decrypt(row["description"], SECRET_KEY) if row["description"] else ""
    except (DecryptionError, ValueError, TypeError, ArithmeticError):
        locked = UNREADABLE

    stamp = str(row["transaction_date"] or "")
    kind, link = PLAIN, None
    if locked:
        pass
    elif row["status"] == "pending":
        locked = PENDING
    else:
        try:
            link = read_record_link(cursor, row["id"])
        except (DecryptionError, ValueError, TypeError):
            link = None
        if link is not None and link["kind"] in FIXED:
            kind = link["kind"]
        elif row["type"] not in _OPPOSITE or row["category"] in SYSTEM_CATEGORIES:
            locked = LINKED
        elif _has_installment_plan(cursor, row["account_id"], stamp):
            kind = INSTALLMENT

    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "amount": amount,
        "type": row["type"],
        "category": row["category"] or "",
        "description": description,
        "date": stamp,
        "locked": locked,
        "kind": kind,
        "fixed": FIXED[kind] if not locked else (),
        "link": link,
    }


def get_transaction(transaction_id) -> dict:
    """The transaction as a form needs it.

    `locked` says why nothing about it can change; `fixed` names the fields
    that cannot when the rest can.
    """
    conn = get_connection()
    try:
        return _load(conn.cursor(), transaction_id)
    finally:
        conn.close()


def _changed() -> None:
    from services.asset_service import mark_financial_data_changed

    mark_financial_data_changed()


def _take_back(cursor, record) -> None:
    """Removes a record and takes its effect back out of its account."""
    adjust_account_balance(
        cursor, record["account_id"], _OPPOSITE[_direction(record["type"])], record["amount"],
        ref_id=record["id"], source="transaction_removed", effective_at=record["date"],
    )
    cursor.execute("DELETE FROM transactions WHERE id = ?", (record["id"],))
    cursor.execute("DELETE FROM anomaly_dismissals WHERE transaction_id = ?", (record["id"],))
    drop_record_link(cursor, record["id"])


def _other_half(cursor, record):
    """The record on the other account of a card payment, if it is still there."""
    partner = record["link"]["ref_id"]
    try:
        return _load(cursor, partner) if partner is not None else None
    except ValueError:
        # The card was removed, and its side of the payment with it.
        return None


def _return_installments(cursor, record) -> None:
    count = int(record["link"]["detail"].get("count") or 0)
    debt = cursor.execute(
        "SELECT paid_installments FROM active_debts WHERE id = ?", (record["link"]["ref_id"],)
    ).fetchone()
    if debt is None or count <= 0:
        return
    # The month it was taken for stays settled: automatic payment does not
    # take it a second time, the debt simply runs that much longer.
    cursor.execute(
        "UPDATE active_debts SET paid_installments = ?, is_active = 1 WHERE id = ?",
        (max(0, debt["paid_installments"] - count), record["link"]["ref_id"]),
    )


def _remove_holding(cursor, record) -> None:
    """Takes back the holding a purchase created, while it is still whole."""
    bought = decimal_from(record["link"]["detail"].get("quantity") or 0)
    holding = cursor.execute(
        "SELECT quantity FROM active_assets WHERE id = ?", (record["link"]["ref_id"],)
    ).fetchone()
    if holding is None or decimal_from(decrypt(holding["quantity"], SECRET_KEY)) != bought:
        raise ValueError(SOLD_SINCE)
    cursor.execute("DELETE FROM active_assets WHERE id = ?", (record["link"]["ref_id"],))


def _restore_holding(cursor, record) -> None:
    """Puts back what a sale took out of a holding, or the holding itself."""
    detail = record["link"]["detail"]
    sold = decimal_from(detail.get("quantity") or 0)
    holding = cursor.execute(
        "SELECT quantity FROM active_assets WHERE id = ?", (record["link"]["ref_id"],)
    ).fetchone()
    if holding is not None:
        held = decimal_from(decrypt(holding["quantity"], SECRET_KEY)) + sold
        cursor.execute(
            "UPDATE active_assets SET quantity = ? WHERE id = ?",
            (encrypt(str(held), SECRET_KEY), record["link"]["ref_id"]),
        )
        return
    cursor.execute(
        "INSERT INTO active_assets"
        " (id, asset_name, asset_code, asset_type, purchase_price, quantity, purchase_date)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            record["link"]["ref_id"], detail.get("name"), detail.get("code"), detail.get("type"),
            encrypt(str(Decimal(str(detail.get("purchase_price")))), SECRET_KEY),
            encrypt(str(sold), SECRET_KEY), detail.get("purchase_date"),
        ),
    )


def delete_transaction(transaction_id) -> dict:
    """Removes a transaction and takes its effect back out of the account.

    For a record the application wrote, the other half is undone in the same
    commit.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        current = _load(cursor, transaction_id)
        if current["locked"]:
            raise ValueError(current["locked"])
        kind = current["kind"]
        if kind == ASSET_PURCHASE:
            _remove_holding(cursor, current)
        elif kind == ASSET_SALE:
            _restore_holding(cursor, current)
        elif kind == DEBT_PAYMENT:
            _return_installments(cursor, current)
        elif kind == CARD_PAYMENT:
            partner = _other_half(cursor, current)
            if partner is not None and not partner["locked"]:
                _take_back(cursor, partner)
        elif kind == INSTALLMENT:
            cursor.execute(
                "DELETE FROM installment_plans WHERE account_id = ? AND created_at = ?",
                (current["account_id"], current["date"]),
            )
        _take_back(cursor, current)
        conn.commit()
    finally:
        # Closing without a commit discards everything since BEGIN.
        conn.close()
    _changed()
    return current


def _stamp(transaction_date, previous: str) -> str:
    """The new date with the old time of day, so same-day order is kept."""
    text = str(transaction_date or "").strip()
    try:
        day = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(BAD_DATE) from None
    if day > datetime.now().date():
        raise ValueError(FUTURE)
    clock = text[11:19] or previous[11:19] or "12:00:00"
    return f"{day.isoformat()} {clock}"


def _move_to_day(cursor, record, stamp) -> None:
    """Moves a record to another day without touching anything else on it."""
    direction = _direction(record["type"])
    adjust_account_balance(
        cursor, record["account_id"], _OPPOSITE[direction], record["amount"],
        ref_id=record["id"], source="transaction_removed", effective_at=record["date"],
    )
    adjust_account_balance(
        cursor, record["account_id"], direction, record["amount"],
        ref_id=record["id"], effective_at=stamp,
    )
    cursor.execute(
        "UPDATE transactions SET transaction_date = ?, execution_date = ? WHERE id = ?",
        (stamp, stamp, record["id"]),
    )


def _update_plan(cursor, record, amount, description, stamp) -> None:
    plan = cursor.execute(
        "SELECT id, total_installments FROM installment_plans"
        " WHERE account_id = ? AND created_at = ?", (record["account_id"], record["date"]),
    ).fetchone()
    if plan is None:
        return
    monthly = fiat(decimal_from(amount) / plan["total_installments"])
    cursor.execute(
        "UPDATE installment_plans SET description = ?, total_amount = ?, monthly_amount = ?,"
        " created_at = ? WHERE id = ?",
        (
            encrypt(str(description or ""), SECRET_KEY), encrypt(str(amount), SECRET_KEY),
            encrypt(str(monthly), SECRET_KEY), stamp, plan["id"],
        ),
    )


def update_transaction(transaction_id, amount, category, description, transaction_date,
                       account_id=None, kind=None) -> dict:
    """Rewrites a transaction's amount, category, description and date.

    With `account_id` it moves to that account, and with `kind` it turns from
    spending into income or back. Left out, both stay as they are.

    Fields that are fixed for the kind of record keep their value whatever is
    asked for: on a record the application wrote, only the date moves.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        current = _load(cursor, transaction_id)
        if current["locked"]:
            raise ValueError(current["locked"])
        fixed = current["fixed"]
        stamp = _stamp(transaction_date, current["date"])

        if "amount" in fixed:
            # One of the application's own records: the day is all that moves.
            if current["kind"] == CARD_PAYMENT:
                partner = _other_half(cursor, current)
                if partner is not None and not partner["locked"]:
                    _move_to_day(cursor, partner, stamp)
            _move_to_day(cursor, current, stamp)
            if current["kind"] == ASSET_PURCHASE:
                cursor.execute(
                    "UPDATE active_assets SET purchase_date = ? WHERE id = ?",
                    (stamp, current["link"]["ref_id"]),
                )
            conn.commit()
            result = {**current, "date": stamp}
        else:
            amount = fiat(amount)
            if amount <= 0:
                raise ValueError("İşlem tutarı 0'dan büyük olmalıdır.")
            amount = float(amount)
            category = str(category or "").strip()
            kind = current["type"] if kind is None or "kind" in fixed else str(kind)
            if kind not in _OPPOSITE:
                raise ValueError(BAD_KIND)
            if account_id is None or "account" in fixed:
                account_id = current["account_id"]
            account_id = int(account_id)
            known = cursor.execute(
                "SELECT 1 FROM categories WHERE name = ? AND type = ?", (category, kind)
            ).fetchone()
            if known is None or category in SYSTEM_CATEGORIES:
                raise ValueError(BAD_CATEGORY)

            # The old effect leaves the account it was made on, as it was made.
            adjust_account_balance(
                cursor, current["account_id"], _OPPOSITE[current["type"]], current["amount"],
                ref_id=current["id"], source="transaction_removed", effective_at=current["date"],
            )
            # Decided with the old amount already taken back, so only the
            # difference counts against a card's limit. An account that is
            # gone is refused here as well.
            AccountService.assert_spending_allowed(cursor, account_id, amount, kind)
            adjust_account_balance(
                cursor, account_id, kind, amount, ref_id=current["id"], effective_at=stamp,
            )
            cursor.execute(
                "UPDATE transactions SET account_id = ?, type = ?, amount = ?, category = ?,"
                " description = ?, transaction_date = ?, execution_date = ? WHERE id = ?",
                (
                    account_id, kind, encrypt(str(amount), SECRET_KEY), category,
                    encrypt(str(description or ""), SECRET_KEY), stamp, stamp, current["id"],
                ),
            )
            if current["kind"] == INSTALLMENT:
                _update_plan(cursor, current, amount, description, stamp)
            conn.commit()
            result = {**current, "account_id": account_id, "type": kind, "amount": amount,
                      "category": category, "description": str(description or ""),
                      "date": stamp}
    finally:
        # Closing without a commit discards everything since BEGIN.
        conn.close()
    _changed()
    return result
