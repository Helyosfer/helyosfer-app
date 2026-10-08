"""Multi-account and credit-card service.

The single point that reads and writes the accounts table. The real work here
is converting the SIGNED value in the raw `balance` column (see
database/db.py::adjust_account_balance) into the fields the UI expects: a
positive `debt` and `available_limit` for credit cards, a plain `balance` for
checking accounts.

Note: the account name is not encrypted. In other tables (active_debts,
recurring_payments) the name is held AES-encrypted, but accounts.name is
already seeded unencrypted at application startup ("Nakit", "Banka", "Kredi
Kartı") and is used as plain text in SUM/JOIN queries; encrypting it after
the fact would make existing rows unreadable.

"""
from contextlib import closing

from database.db import ACCOUNT, get_connection, record_balance_event
from utils.financial_decimal import fiat

CHECKING = "checking"
CREDIT_CARD = "credit_card"


ACCOUNT_TYPE_LABELS = {
    CHECKING: "Nakit / Vadesiz",
    CREDIT_CARD: "Kredi Kartı",
}


def _fmt_try(value):
    """Writes the amount in Turkish format (TRY 1.234,56) -- so error
    messages shown to the user use the same format as the rest of the
    application.
    """
    return f"₺{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class AccountService:

    @staticmethod
    def create_account(name, account_type, initial_balance=0.0,
                       credit_limit=0.0, statement_date=None,
                       card_number_full=None):
        """Creates a new account/card and returns the id of the inserted row.

        For a credit card, `initial_balance` is expected as the CURRENT DEBT
        (a positive number) and is written to the database as a negative
        balance -- the caller does not have to flip the sign; the user says "I
        owe 5000 lira" and we write -5000.

        `card_number_full` exists in raw form ONLY for the lifetime of this
        function -- it is used here to derive the last four digits and the
        card network, and is never encrypted and written to disk. The full card number, expiry date and
        CVC used to be encrypted and kept in persistent columns -- the
        interface only ever displayed the last four digits and the network, so
        storing them had no product justification. The `expiry_date`/`cvc_code`
        parameters were removed entirely; they had no consumers.

        Raises ValueError for: an empty name, a negative amount, a credit card
        with no limit or an opening debt larger than the limit, an invalid
        statement day.
        """
        name = (name or "").strip()
        if not name:
            raise ValueError("Hesap adı boş olamaz.")
        if account_type not in (CHECKING, CREDIT_CARD):
            raise ValueError(f"Bilinmeyen hesap türü: {account_type}")

        try:
            initial_balance = float(fiat(0 if initial_balance is None else initial_balance))
            credit_limit = float(fiat(0 if credit_limit is None else credit_limit))
        except (TypeError, ValueError) as exc:
            raise ValueError("Tutar ve limit sonlu sayısal olmalıdır.") from exc

        if statement_date not in (None, ""):
            try:
                statement_date = int(statement_date)
            except (TypeError, ValueError):
                raise ValueError("Hesap kesim günü 1-31 arası bir sayı olmalıdır.")
            if not 1 <= statement_date <= 31:
                raise ValueError("Hesap kesim günü 1-31 arası olmalıdır.")
        else:
            statement_date = None

        if account_type == CREDIT_CARD:
            if credit_limit <= 0:
                raise ValueError("Kredi kartı için 0'dan büyük bir limit girilmelidir.")
            if initial_balance < 0:
                raise ValueError("Mevcut borç negatif olamaz.")
            if initial_balance > credit_limit:
                raise ValueError("Mevcut borç, kart limitini aşamaz.")

            balance = -initial_balance
            legacy_type = "credit"
        else:
            balance = initial_balance
            credit_limit = 0.0
            statement_date = None
            legacy_type = "bank"


        masked_number = None
        network_logo = None
        if card_number_full:
            network_logo = AccountService.check_card_network(card_number_full)
            last4 = card_number_full[-4:] if len(card_number_full) >= 4 else card_number_full
            masked_number = f"**** **** **** {last4}"

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO accounts (name, type, balance, account_type, credit_limit, statement_date, masked_number, network_logo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (name, legacy_type, balance, account_type, credit_limit, statement_date, masked_number, network_logo))
            account_id = cursor.lastrowid
            record_balance_event(cursor, ACCOUNT, account_id, balance, balance,
                                 "account_opened")
            conn.commit()
            return account_id
        finally:
            conn.close()

    @staticmethod
    def check_card_network(card_number):
        """Determines the network from the leading digits of the card number (IIN/BIN).

        Logo paths are kept in one place in database/db.py::NETWORK_LOGOS and
        are not repeated here, so the two do not diverge when an asset path
        changes.

        ORDER MATTERS: Troy cards start with 9792 and Mastercard with 5 -- the
        prefix check has to start from the longest/most specific, otherwise a
        9792... number would match no rule and come back empty.
        """
        from database.db import NETWORK_LOGOS

        if not card_number:
            return ""
        num = "".join(ch for ch in str(card_number) if ch.isdigit())
        if not num:
            return ""
        if num.startswith("9792"):
            return NETWORK_LOGOS.get("Troy", "")
        if num.startswith("4"):
            return NETWORK_LOGOS.get("Visa", "")
        if num[0] in ("5", "2"):
            return NETWORK_LOGOS.get("Mastercard", "")
        return ""

    @staticmethod
    def _to_dict(row):
        account_type = row["account_type"]
        if not account_type:
            account_type = CREDIT_CARD if row["type"] == "credit" else CHECKING

        balance = float(row["balance"] or 0)
        credit_limit = float(row["credit_limit"] or 0)


        has_masked_number = bool(
            "masked_number" in row.keys() and row["masked_number"]
        )
        masked_number = row["masked_number"] if has_masked_number else "**** **** **** 0000"
        network_logo = (row["network_logo"] or "") if "network_logo" in row.keys() else ""
        is_frozen = bool(
            row["is_frozen"]
            if "is_frozen" in row.keys() and row["is_frozen"] is not None
            else 0
        )
        online_payments_enabled = bool(
            row["online_payments_enabled"]
            if (
                "online_payments_enabled" in row.keys()
                and row["online_payments_enabled"] is not None
            )
            else 1
        )

        if account_type == CREDIT_CARD:
            if balance > 0:
                debt = 0.0
                available_limit = credit_limit + balance
            else:
                debt = max(0.0, -balance)
                available_limit = max(0.0, credit_limit - debt)
        else:
            debt = 0.0
            available_limit = 0.0

        return {
            "id": row["id"],
            "name": row["name"],
            "account_type": account_type,
            "type_label": ACCOUNT_TYPE_LABELS.get(account_type, account_type),
            "balance": round(balance, 2),
            "credit_limit": round(credit_limit, 2),
            "statement_date": row["statement_date"],
            "debt": round(debt, 2),
            "available_limit": round(available_limit, 2),
            "masked_number": masked_number,
            "network_logo": network_logo,
            "is_frozen": is_frozen,
            "online_payments_enabled": online_payments_enabled,


            "has_card_number": has_masked_number,
        }

    @staticmethod
    def get_accounts():
        """Returns every account with its derived fields (checking accounts first)."""
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT * FROM accounts
                ORDER BY CASE WHEN account_type = 'credit_card' THEN 1 ELSE 0 END, id
            """).fetchall()
        finally:
            conn.close()
        return [AccountService._to_dict(r) for r in rows]

    @staticmethod
    def get_account(account_id):
        """Returns a single account, or None if it does not exist."""
        conn = get_connection()
        try:
            row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        finally:
            conn.close()
        return AccountService._to_dict(row) if row else None

    @staticmethod
    def account_exists(account_id):
        """Does the account exist? (A fast check that does not need to decrypt
        the whole row.)

        Flows that write transactions use this as a precondition: since the
        default account seed was removed, DEFAULT_ACCOUNT_ID matches no row on
        a fresh installation, and without the check ownerless records were
        being created.
        """
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT 1 FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    @staticmethod
    def has_any_account():
        """Has the user created any account at all? The condition for the onboarding gate."""
        conn = get_connection()
        try:
            row = conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone()
        finally:
            conn.close()
        return row is not None

    @staticmethod
    def get_net_worth():
        """Returns net worth together with its components.

        net = total cash - total card debt. Thanks to the signed convention
        this is exactly the same number as a plain SUM(balance); the reason it
        is computed separately here is so the UI can show a breakdown such as
        "Cash TRY 17,300 / Card debt TRY 3,500".
        """
        cash = 0.0
        card_debt = 0.0
        for acc in AccountService.get_accounts():
            if acc["account_type"] == CREDIT_CARD:
                card_debt += acc["debt"]
            else:
                cash += acc["balance"]
        return {
            "cash": round(cash, 2),
            "card_debt": round(card_debt, 2),
            "net": round(cash - card_debt, 2),
        }

    @staticmethod
    def _set_card_preference(account_id, column, enabled):
        """Persists the card usage preference and refreshes the in-memory snapshot."""
        if column not in {"is_frozen", "online_payments_enabled"}:
            raise ValueError("Bilinmeyen kart tercihi.")
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE accounts SET {column} = ? WHERE id = ?",
                (int(bool(enabled)), int(account_id)),
            )
            if cursor.rowcount != 1:
                raise ValueError("Hesap bulunamadı.")
            conn.commit()
        finally:
            conn.close()


        from services.asset_service import refresh_account_cache_snapshot
        refresh_account_cache_snapshot()
        return True

    @staticmethod
    def set_card_frozen(account_id, frozen):
        """Persists that the account is closed to new income/expense transactions."""
        return AccountService._set_card_preference(
            account_id, "is_frozen", frozen
        )

    @staticmethod
    def set_online_payments(account_id, enabled):
        """Stores the online-shopping preference.

        Because the transaction model carries no online/offline attribute,
        this preference does not block spending today; the UI presents it
        explicitly as a preference.
        """
        return AccountService._set_card_preference(
            account_id, "online_payments_enabled", enabled
        )

    @staticmethod
    def assert_spending_allowed(
            cursor, account_id, amount, transaction_type="expense", *,
            enforce_limits=True):
        """The SAME rule as `check_spending_allowed` -- but it decides from THE
        CALLER's cursor and raises `ValueError` on a violation.

        WHY IT EXISTS: the decision and the write that follows it have to be
        in the SAME transaction. A check that reads from a separate connection
        cannot see a commit that lands between the decision and the write
        (TOCTOU): two concurrent spends could consume the same limit snapshot.
        `transaction_service` had solved this with `BEGIN IMMEDIATE` plus the
        same cursor, but by COPYING the rule into itself.
        `asset_purchase_service` did not copy it and left the check outside
        the transaction -- on a card with a 100-lira limit, two concurrent
        purchases could push the debt to 120 lira.

        The rule now lives in one place. The caller must call this AFTER
        taking the write lock with `BEGIN IMMEDIATE`; this function serialises
        nothing on its own and only looks at the state the given cursor
        sees.
        """
        row = cursor.execute(
            "SELECT account_type, type, balance, credit_limit, is_frozen "
            "FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Hesap bulunamadı (id={account_id}).")
        if bool(row["is_frozen"]):
            raise ValueError(
                "Bu kart dondurulduğu için işlem yapılamaz. "
                "İşlem yapmak için önce kartın dondurmasını kaldırın."
            )
        if transaction_type not in ("expense", "Gider") or not enforce_limits:
            return
        try:
            amount = fiat(amount)
        except (TypeError, ValueError) as exc:
            raise ValueError("Geçersiz tutar.") from exc


        account_type = row["account_type"] or (
            "credit_card" if row["type"] == "credit" else CHECKING
        )
        if account_type != CREDIT_CARD:


            return


        limit = fiat(row["credit_limit"] or 0)
        if limit <= 0:
            return


        debt = fiat(max(0.0, -float(row["balance"] or 0)))


        if fiat(debt + amount) > limit:
            raise ValueError(
                f"Limit yetersiz: kullanılabilir limit "
                f"{_fmt_try(float(limit - debt))}, harcama "
                f"{_fmt_try(float(amount))}."
            )

    @staticmethod
    def check_spending_allowed(
            account_id, amount, transaction_type="expense",
            enforce_limits=True):
        """Checks whether the account is eligible for a new income/expense transaction.

        Returns (is_allowed, error_message). On frozen accounts every new
        transaction is rejected, income included. On checking accounts an
        expense is NO LONGER limited by the available balance -- the user may
        deliberately go negative; on a credit card the limit is still
        enforced. Debt payment does not pass through this function and can be
        made to a frozen card.

        CAREFUL -- this is the ASKING form: it opens its own connection, and
        that connection closes the moment it returns the answer. So the answer
        CAN GO STALE before the caller uses it. Do not use it as a guard in
        front of a write; `assert_spending_allowed` exists for that. This
        belongs in UI pre-checks that inform the user before writing.
        """
        with closing(get_connection()) as conn:
            try:
                AccountService.assert_spending_allowed(
                    conn.cursor(), account_id, amount, transaction_type,
                    enforce_limits=enforce_limits,
                )
            except ValueError as exc:
                return False, str(exc)
        return True, ""

    @staticmethod
    def pay_credit_card_debt(credit_card_id, source_account_id, amount):
        """Pays credit-card debt from a checking account."""


        try:
            amount = float(fiat(amount))
        except (TypeError, ValueError) as exc:
            raise ValueError("Ödenecek tutar geçerli bir sayı olmalıdır.") from exc
        if amount <= 0:
            raise ValueError("Ödenecek tutar sıfırdan büyük olmalıdır.")

        card = AccountService.get_account(credit_card_id)
        if not card or card["account_type"] != CREDIT_CARD:
            raise ValueError("Geçersiz kredi kartı.")

        debt = float(card["debt"])
        if debt <= 0:
            raise ValueError("Bu kredi kartında ödenecek borç bulunmuyor.")
        if amount > debt:
            raise ValueError(
                f"Ödeme mevcut borcu aşamaz. Güncel borç: {_fmt_try(debt)}."
            )

        source = AccountService.get_account(source_account_id)
        if not source or source["account_type"] != CHECKING:
            raise ValueError("Ödeme yapılacak hesap vadesiz hesap olmalıdır.")

        conn = get_connection()
        try:
            cursor = conn.cursor()


            cursor.execute(
                "UPDATE accounts SET balance = balance - ?"
                " WHERE id = ? AND account_type = ?",
                (amount, source_account_id, CHECKING),
            )
            if cursor.rowcount != 1:
                raise ValueError("Hesap bakiyesi güncellenemedi.")

            cursor.execute(
                "UPDATE accounts SET balance = balance + ?"
                " WHERE id = ? AND account_type = ? AND balance <= ?",
                (amount, credit_card_id, CREDIT_CARD, -amount),
            )
            if cursor.rowcount != 1:
                raise ValueError("Ödeme mevcut kart borcunu aşamaz.")


            from database.db import record_balance_event, ACCOUNT
            cursor.execute("SELECT balance FROM accounts WHERE id = ?", (source_account_id,))
            new_source_balance = cursor.fetchone()["balance"]
            record_balance_event(cursor, ACCOUNT, source_account_id, -amount, new_source_balance, "card_payment")

            cursor.execute("SELECT balance FROM accounts WHERE id = ?", (credit_card_id,))
            new_card_balance = cursor.fetchone()["balance"]
            record_balance_event(cursor, ACCOUNT, credit_card_id, amount, new_card_balance, "card_payment")


            from services.transaction_service import SECRET_KEY
            from utils.crypto import encrypt
            import datetime
            date_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            enc_amount = encrypt(str(amount), SECRET_KEY)
            desc = f"{card['name']} Borç Ödemesi"
            enc_desc = encrypt(desc, SECRET_KEY)

            cursor.execute("""
                INSERT INTO transactions (account_id, amount, type, category, description, transaction_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (source_account_id, enc_amount, "expense", "Borç Ödeme", enc_desc, date_now))


            cursor.execute("""
                INSERT INTO transactions (account_id, amount, type, category, description, transaction_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (credit_card_id, enc_amount, "payment", "Borç Ödeme", enc_desc, date_now))

            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def delete_credit_card(credit_card_id):
        """Deletes the card and all of its dependent records in a single transaction."""
        credit_card_id = int(credit_card_id)
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            card = cursor.execute(
                "SELECT id FROM accounts WHERE id = ? AND account_type = ?",
                (credit_card_id, CREDIT_CARD),
            ).fetchone()
            if card is None:
                raise ValueError("Kredi kartı bulunamadı.")


            has_installment_table = cursor.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'installment_plans'"""
            ).fetchone()
            if has_installment_table:
                cursor.execute(
                    "DELETE FROM installment_plans WHERE account_id = ?",
                    (credit_card_id,),
                )
            cursor.execute(
                "DELETE FROM recurring_payments WHERE account_id = ?",
                (credit_card_id,),
            )
            cursor.execute(
                "DELETE FROM transactions WHERE account_id = ?",
                (credit_card_id,),
            )
            cursor.execute(
                "DELETE FROM balance_events WHERE entity_type = ? AND entity_id = ?",
                (ACCOUNT, credit_card_id),
            )
            cursor.execute(
                "DELETE FROM accounts WHERE id = ? AND account_type = ?",
                (credit_card_id, CREDIT_CARD),
            )
            if cursor.rowcount != 1:
                raise ValueError("Kredi kartı bulunamadı.")
            conn.commit()


            from services.asset_service import mark_account_cache_stale
            mark_account_cache_stale()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def get_active_installment_plan_count(credit_card_id):
        """Returns the number of unfinished instalment plans on the card."""
        conn = get_connection()
        try:
            table_exists = conn.execute(
                """SELECT 1 FROM sqlite_master
                   WHERE type = 'table' AND name = 'installment_plans'"""
            ).fetchone()
            if not table_exists:
                return 0
            row = conn.execute(
                """SELECT COUNT(*) AS plan_count
                   FROM installment_plans
                   WHERE account_id = ?
                     AND paid_installments < total_installments""",
                (int(credit_card_id),),
            ).fetchone()
            return int(row["plan_count"] if row else 0)
        finally:
            conn.close()
