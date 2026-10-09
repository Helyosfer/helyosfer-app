"""Changing and removing a transaction the user entered.

A transaction's effect on its account is undone and, for a change, applied
again in the same commit, on the ledger day the transaction belongs to. The
balance, the ledger and the row therefore never disagree.

Transactions the application writes on its own (a loan installment, a card
payment, an asset trade, an installment purchase) are one half of a larger
record. Changing that half alone would leave the other half wrong, so they
are refused here and are undone where they were made.
"""

from __future__ import annotations

from datetime import datetime

from database.db import adjust_account_balance, get_connection
from services.account_service import AccountService
from services.transaction_service import SECRET_KEY
from utils.crypto import decrypt, encrypt
from utils.errors import DecryptionError
from utils.financial_decimal import fiat

# Categories written by the application itself; never offered in a form.
SYSTEM_CATEGORIES = ("Varlık Alımı", "Varlık Satışı", "Kredi Taksiti", "Borç Ödeme")

NOT_FOUND = "İşlem bulunamadı."
LINKED = "Bu işlem uygulama tarafından oluşturuldu ve buradan değiştirilemez."
INSTALLMENT = "Taksitli bir alışveriş buradan değiştirilemez."
PENDING = "Bekleyen bir işlem Borçlar ve ödemeler bölümünden değiştirilir."
UNREADABLE = "Bu kayıt okunamadığı için değiştirilemez."
FUTURE = "İşlem tarihi gelecekte olamaz."
BAD_DATE = "İşlem tarihi geçersiz."
BAD_CATEGORY = "Bu kategori bu işlem türü için kullanılamaz."
BAD_KIND = "İşlem türü geçersiz."

_OPPOSITE = {"income": "expense", "expense": "income"}


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
    """The row with its amount decrypted and the reason it is locked, if any."""
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
    if locked:
        pass
    elif row["status"] == "pending":
        locked = PENDING
    elif row["type"] not in _OPPOSITE or row["category"] in SYSTEM_CATEGORIES:
        locked = LINKED
    elif _has_installment_plan(cursor, row["account_id"], stamp):
        locked = INSTALLMENT

    return {
        "id": row["id"],
        "account_id": row["account_id"],
        "amount": amount,
        "type": row["type"],
        "category": row["category"] or "",
        "description": description,
        "date": stamp,
        "locked": locked,
    }


def get_transaction(transaction_id) -> dict:
    """The transaction as a form needs it; `locked` says why it cannot change."""
    conn = get_connection()
    try:
        return _load(conn.cursor(), transaction_id)
    finally:
        conn.close()


def _changed() -> None:
    from services.asset_service import mark_financial_data_changed

    mark_financial_data_changed()


def delete_transaction(transaction_id) -> dict:
    """Removes a transaction and takes its effect back out of the account."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        current = _load(cursor, transaction_id)
        if current["locked"]:
            raise ValueError(current["locked"])
        adjust_account_balance(
            cursor, current["account_id"], _OPPOSITE[current["type"]], current["amount"],
            ref_id=current["id"], source="transaction_removed", effective_at=current["date"],
        )
        cursor.execute("DELETE FROM transactions WHERE id = ?", (current["id"],))
        cursor.execute(
            "DELETE FROM anomaly_dismissals WHERE transaction_id = ?", (current["id"],)
        )
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


def update_transaction(transaction_id, amount, category, description, transaction_date,
                       account_id=None, kind=None) -> dict:
    """Rewrites a transaction's amount, category, description and date.

    With `account_id` it moves to that account, and with `kind` it turns from
    spending into income or back. Left out, both stay as they are.
    """
    amount = fiat(amount)
    if amount <= 0:
        raise ValueError("İşlem tutarı 0'dan büyük olmalıdır.")
    amount = float(amount)
    category = str(category or "").strip()

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        current = _load(cursor, transaction_id)
        if current["locked"]:
            raise ValueError(current["locked"])
        kind = current["type"] if kind is None else str(kind)
        if kind not in _OPPOSITE:
            raise ValueError(BAD_KIND)
        account_id = current["account_id"] if account_id is None else int(account_id)
        known = cursor.execute(
            "SELECT 1 FROM categories WHERE name = ? AND type = ?", (category, kind)
        ).fetchone()
        if known is None or category in SYSTEM_CATEGORIES:
            raise ValueError(BAD_CATEGORY)
        stamp = _stamp(transaction_date, current["date"])

        # The old effect leaves the account it was made on, as it was made.
        adjust_account_balance(
            cursor, current["account_id"], _OPPOSITE[current["type"]], current["amount"],
            ref_id=current["id"], source="transaction_removed", effective_at=current["date"],
        )
        # Decided with the old amount already taken back, so only the
        # difference counts against a card's limit. An account that is gone
        # is refused here as well.
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
        conn.commit()
    finally:
        # Closing without a commit discards everything since BEGIN.
        conn.close()
    _changed()
    return {**current, "account_id": account_id, "type": kind,
            "amount": amount, "category": category,
            "description": str(description or ""), "date": stamp}
