import sqlite3

from utils.errors import (
    HelyosferError,
    DecryptionError,
    FinancialDataIntegrityError,
    KeyUnavailableError,
)
from database.db import (
    COMPLETED_TX, COMPLETED_TX_T, get_connection, managed_connection,
    adjust_account_balance,
)
from services.account_service import AccountService
from utils.crypto import encrypt, decrypt
from utils.financial_decimal import decimal_from, fiat
from datetime import datetime

SECRET_KEY = "fi" + "nora_secure_2026"


_INSTALLMENTS_TABLE = "installment_plans"


def _period_date_cond(filter_type: str, column: str) -> str:
    """Converts the dashboard period filter (Today/1 Week/...) into a SQL date
    condition. `get_transactions_by_period` and the opening-balance query must
    use THE SAME period definition -- otherwise, under the "Today" filter,
    transactions would be read from one date range and the opening balance
    from another.

    `column` must be a column/expression that already exists in the caller's
    SQL (for example "t.transaction_date", "ts"); because the values come only
    from this fixed list, embedding it in an f-string is safe (user input never
    enters).
    """
    if filter_type == "1 Hafta":
        return f"date({column}) >= date('now', '-7 days', 'localtime')"
    if filter_type == "1 Ay":
        return f"date({column}) >= date('now', '-1 month', 'localtime')"
    if filter_type == "1 Yıl":
        return f"date({column}) >= date('now', '-1 year', 'localtime')"
    if filter_type == "Hayat Boyu":
        return f"date({column}) IS NOT NULL"
    return f"date({column}) = date('now', 'localtime')"


def _ensure_installments_table(cursor) -> None:
    """Amounts are held as encrypted TEXT as in the other tables (not
    aggregated in SQL, decrypted in Python); the instalment counters stay
    plain, queryable INTEGERs.
    """
    cursor.execute(f"""CREATE TABLE IF NOT EXISTS {_INSTALLMENTS_TABLE} (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        account_id INTEGER NOT NULL,
        description TEXT NOT NULL,
        total_amount TEXT NOT NULL,
        monthly_amount TEXT NOT NULL,
        total_installments INTEGER NOT NULL,
        paid_installments INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )""")


class TransactionService:
    @staticmethod
    def add_transaction(account_id, amount, transaction_type, category, description,
                        transaction_date=None, enforce_credit_limit=True,
                        installments=None, detect_subscription=True):
        """If transaction_date is not given, now is used; back-dated records such
        as a CSV import pass the date explicitly -- they will have gone through
        the same atomic path, balance synchronisation included.

        For expenses on a credit card the available limit is checked and
        ValueError is raised if it is exceeded. Callers that reconstruct
        history as it was, such as a CSV import, can pass
        `enforce_credit_limit=False` -- otherwise a real past spend that
        pushed the limit could not be imported.

        If `installments` (2-12) is given, the transaction is an instalment
        credit-card spend: the whole amount is charged to the card at once (the
        bank blocks the full amount against the limit), and in THE SAME commit
        a monthly instalment plan is added to installment_plans (monthly amount
        = total / number of instalments). That way the transaction and the plan
        can never come apart.
        """
        # This is the shared service boundary for user/API/import monetary
        # input.  SQLite must never be allowed to decide what NaN/Infinity
        # means for a financial operation.
        amount = fiat(amount)
        if amount <= 0:
            raise ValueError("İşlem tutarı 0'dan büyük olmalıdır.")
        # sqlite3 has no Decimal adapter; all persisted money in this legacy
        # schema is REAL, so pass the already-quantized finite value only.
        amount = float(amount)
        if installments is not None:
            installments = int(installments)
            if not 1 <= installments <= 12:
                raise ValueError("Taksit sayısı 1 ile 12 arasında olmalıdır.")
            if installments == 1:
                installments = None


        conn = get_connection()
        try:
            cursor = conn.cursor()
            # The limit decision and the balance write must observe the same
            # SQLite snapshot. BEGIN IMMEDIATE serializes competing card
            # charges before either can consume the same available limit.
            cursor.execute("BEGIN IMMEDIATE")


            AccountService.assert_spending_allowed(
                cursor, account_id, amount, transaction_type,
                enforce_limits=enforce_credit_limit,
            )


            str_amount = str(amount)
            encrypted_amount = encrypt(str_amount, SECRET_KEY)
            encrypted_description = encrypt(description, SECRET_KEY)


            date_now = transaction_date or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Check if transaction is in the future
            from datetime import datetime as dt
            parsed_date = dt.strptime(date_now[:10], "%Y-%m-%d") if len(date_now) >= 10 else dt.now()
            is_future = parsed_date.date() > dt.now().date()
            status = 'pending' if is_future else 'completed'

            cursor.execute("""
                INSERT INTO transactions (account_id, amount, type, category, description, transaction_date, status, execution_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (account_id, encrypted_amount, transaction_type, category, encrypted_description, date_now, status, date_now))


            if not is_future:
                adjust_account_balance(
                    cursor, account_id, transaction_type, amount, effective_at=date_now,
                )

            if installments:


                monthly = fiat(decimal_from(amount) / installments)
                _ensure_installments_table(cursor)
                cursor.execute(f"""
                    INSERT INTO {_INSTALLMENTS_TABLE}
                        (account_id, description, total_amount, monthly_amount,
                         total_installments, paid_installments, created_at)
                    VALUES (?, ?, ?, ?, ?, 0, ?)
                """, (
                    account_id,
                    encrypted_description,
                    encrypt(str(amount), SECRET_KEY),
                    encrypt(str(monthly), SECRET_KEY),
                    installments,
                    date_now,
                ))

            conn.commit()
        finally:
            conn.close()


        if detect_subscription and transaction_type in ("expense", "Gider"):
            try:
                from services.recurring_service import (
                    register_subscription_from_transaction,
                )
                account = AccountService.get_account(account_id)
                is_credit_card = bool(
                    account and account.get("account_type") == "credit_card")
                register_subscription_from_transaction(
                    account_id=account_id,
                    amount=amount,
                    category=category,
                    description=description,
                    transaction_date=date_now,
                    is_credit_card=is_credit_card,
                )
            except Exception:
                from utils.logging_config import get_logger
                get_logger().exception("Abonelik radarına yazılamadı")

    @staticmethod
    def settle_due_transactions(today=None):
        """Applies due future-dated transactions to the balance.

        add_transaction writes a future-dated record as status='pending' and
        DOES NOT TOUCH the balance (banking behaviour: the money does not
        appear in the account before the date arrives). This method turns those
        records into 'completed' when they fall due and applies the balance; if
        it is never called, future-dated income/expense never reaches the
        balance at all.

        Each row is processed in its own SAVEPOINT: one corrupt record whose
        amount cannot be decrypted does not block the other due transactions.
        Because the query filters on 'pending' and sets the row to 'completed',
        calling it again is safe (idempotent) -- the same transaction is never
        applied to the balance twice.

        The credit limit is NOT re-checked here: in real life a bill falling
        due is not treated as "unprocessed" because the limit is full; it is
        charged to the card as debt. The limit was checked when the record was
        created.

        Returns the number of transactions applied to the balance.
        """
        reference_day = today or datetime.now().strftime("%Y-%m-%d")

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT t.id, t.account_id, t.amount, t.type, t.execution_date,"
                " COALESCE(a.is_frozen, 0) AS is_frozen"
                " FROM transactions AS t"
                " LEFT JOIN accounts AS a ON a.id = t.account_id"
                " WHERE status = 'pending' AND date(execution_date) <= date(?)"
                " ORDER BY date(execution_date), t.id",
                (reference_day,),
            )
            due_rows = cursor.fetchall()

            settled = 0
            for row in due_rows:


                if bool(row["is_frozen"]):
                    continue
                try:
                    amount = float(decrypt(str(row["amount"]), SECRET_KEY))
                except KeyUnavailableError:
                    raise
                except (DecryptionError, ValueError, TypeError):
                    from utils.logging_config import get_logger
                    get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] pending işlem id={row['id']} tutarı çözülemedi")


                    continue

                cursor.execute("SAVEPOINT settle_tx")
                try:
                    # Settled late, it still belongs to its own day: balances
                    # over time follow the date of the transaction.
                    adjust_account_balance(
                        cursor, row["account_id"], row["type"], amount,
                        ref_id=row["id"], effective_at=row["execution_date"],
                    )
                    cursor.execute(
                        "UPDATE transactions SET status = 'completed' WHERE id = ?",
                        (row["id"],),
                    )
                except (sqlite3.Error, ValueError, HelyosferError):


                    from utils.logging_config import get_logger
                    get_logger().exception(
                        f"Vadesi gelen işlem yerleştirilemedi (id={row['id']}), "
                        "kalan işlemler sürdürülüyor"
                    )
                    cursor.execute("ROLLBACK TO SAVEPOINT settle_tx")
                else:
                    cursor.execute("RELEASE SAVEPOINT settle_tx")
                    settled += 1

            conn.commit()
        finally:
            conn.close()

        return settled

    @staticmethod
    def get_pending_transactions():
        """Returns transactions not yet due (not yet applied to the balance).

        The data source for the "Pending Transactions" panel. Because the
        amount/description are encrypted they are decrypted in Python;
        ordering happens in SQL over a plain column.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, account_id, amount, type, category, description,"
                " execution_date FROM transactions WHERE status = 'pending'"
                " ORDER BY date(execution_date), id"
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        items = []
        for r in rows:
            try:
                amount = float(decrypt(str(r["amount"]), SECRET_KEY))
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] pending işlem id={r['id']} tutarı çözülemedi")
                amount = 0.0
            try:
                description = decrypt(str(r["description"]), SECRET_KEY) or ""
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] pending işlem id={r['id']} açıklaması çözülemedi")
                description = ""
            items.append({
                "id": r["id"],
                "account_id": r["account_id"],
                "amount": amount,
                "type": r["type"],
                "category": r["category"] or "",
                "description": description.strip() or (r["category"] or "İşlem"),
                "execution_date": (r["execution_date"] or "")[:10],
            })
        return items

    @staticmethod
    def cancel_pending_transaction(transaction_id):
        """Deletes a pending transaction.

        Only status='pending' rows are deleted; silently destroying a record
        that has been applied to the balance would separate the balance from
        the ledger. Returns True if it was deleted.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM transactions WHERE id = ? AND status = 'pending'",
                (int(transaction_id),),
            )
            deleted = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        return deleted > 0

    @staticmethod
    def reschedule_pending_transaction(transaction_id, new_date):
        """Changes the due date of a pending transaction.

        If the new date is pulled back to today, the record is applied to the
        balance on its own in the next settle round -- no balance is applied
        separately here, so that the processing logic stays in one place
        (settle_due_transactions).
        """
        day = str(new_date)[:10]
        datetime.strptime(day, "%Y-%m-%d")


        stamp = f"{day} 09:00:00"

        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE transactions SET transaction_date = ?, execution_date = ?"
                " WHERE id = ? AND status = 'pending'",
                (stamp, stamp, int(transaction_id)),
            )
            updated = cursor.rowcount
            conn.commit()
        finally:
            conn.close()
        return updated > 0

    @staticmethod
    def get_installment_plans(account_id):
        """Returns a card's ongoing instalment plans (the ones with instalments left).

        The data source for the 'Upcoming Payments' dialog. Because amounts are
        encrypted TEXT they are decrypted in Python (the same pattern as
        get_recent_for_account). Each element: description, total_amount,
        monthly_amount, total_installments, paid_installments,
        remaining_installments, remaining_amount, created_at.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            _ensure_installments_table(cursor)
            cursor.execute(
                f"SELECT * FROM {_INSTALLMENTS_TABLE}"
                " WHERE account_id = ? AND paid_installments < total_installments"
                " ORDER BY created_at DESC, id DESC",
                (int(account_id),),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()

        plans = []
        for r in rows:
            try:


                total = decimal_from(decrypt(str(r["total_amount"]), SECRET_KEY))
                monthly = decimal_from(
                    decrypt(str(r["monthly_amount"]), SECRET_KEY)
                )
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] taksit planı id={r['id']} tutarı çözülemedi")
                continue


            try:
                plan_description = decrypt(str(r["description"]), SECRET_KEY) or "Taksitli İşlem"
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception(f"[VERİ BÜTÜNLÜĞÜ] taksit planı id={r['id']} açıklaması çözülemedi")
                plan_description = "Taksitli İşlem"
            paid_count = int(r["paid_installments"])
            remaining = int(r["total_installments"]) - paid_count


            remaining_amount = fiat(total - monthly * paid_count)
            plans.append({
                "id": r["id"],
                "description": plan_description,


                "total_amount": float(total),
                "monthly_amount": float(monthly),
                "total_installments": int(r["total_installments"]),
                "paid_installments": paid_count,
                "remaining_installments": remaining,
                "remaining_amount": float(remaining_amount),
                "created_at": r["created_at"],
            })
        return plans

    @staticmethod
    def get_transactions_by_period(filter_type):
        date_cond = _period_date_cond(filter_type, "t.transaction_date")

        with managed_connection() as conn:
            cursor = conn.cursor()


            cursor.execute(f"""
                SELECT t.amount, t.type, t.category, t.transaction_date, c.importance
                FROM transactions t
                LEFT JOIN categories c ON t.category = c.name
                WHERE {date_cond}
                  AND {COMPLETED_TX_T}
            """)
            rows = cursor.fetchall()

        data = []
        for r in rows:
            try:
                decrypted_amount = float(decrypt(r[0], SECRET_KEY))
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError) as exc:


                raise FinancialDataIntegrityError(
                    "transactions", None, "amount", reason=exc
                ) from exc

            data.append({
                'amount': decrypted_amount,
                'type': r[1],
                'category': r[2] if r[2] else 'Diğer',
                'transaction_date': r[3],
                'importance': r[4] if r[4] else 'extra'
            })
        return data

    @staticmethod
    def get_opening_baseline_by_period(filter_type):
        """The total of the (positive) opening balances of accounts opened in the selected period.

        WHY: an account's opening balance is never written to the
        `transactions` table (only accounts.balance +
        balance_events('account_opened') -- see AccountService.create_account).
        As a result the pie/line chart on the My Assets tab was fed entirely
        from `get_transactions_by_period`, and a user with a single NEWLY
        opened account (who had entered no transaction yet) saw "No Data" on
        the chart -- even with a full balance.

        We do NOT WRITE the opening balance as a real "Main Income"
        transaction: it deliberately never touches `transactions`, so
        cash-flow analyses such as the savings rate, the 50-30-20 health score
        and the ODE daily-income input are not inflated by opening balances
        (see DashboardService.get_opening_baseline, the same principle). Only
        for THIS summary is a separate, visible "Opening Balance" slice
        returned.

        A credit card's opening DEBT (a negative delta) is excluded -- a debt
        appearing in the income pie would make no sense.
        """
        return round(
            sum(
                event["amount"]
                for event in TransactionService.get_opening_events_by_period(
                    filter_type)
            ),
            2,
        )

    @staticmethod
    def get_opening_events_by_period(filter_type):
        """Returns the opening balances WITH THEIR TIMESTAMPS (for the chart buckets).

        `get_opening_baseline_by_period` gives only the total; the time chart
        (CurvedTrendChart), however, has to place each event in its own
        hour/day/month bucket and so needs the date as well. THE SAME field
        names as the transaction dictionaries (`amount`, `transaction_date`)
        are used so that `_build_time_buckets` can process both sources in a
        single loop.
        """
        conn = get_connection()
        try:
            date_cond = _period_date_cond(filter_type, "ts")
            rows = conn.execute(f"""
                SELECT ts, delta FROM balance_events
                WHERE entity_type = 'account' AND source = 'account_opened'
                  AND {date_cond}
                ORDER BY ts
            """).fetchall()
        finally:
            conn.close()
        return [
            {"amount": float(row[1]), "transaction_date": row[0]}
            for row in rows
            if row[1] and row[1] > 0
        ]

    @staticmethod
    def get_recent_for_account(account_id, limit=3):
        """Returns a account's/card's recent transactions (date, description, amount).

        The data source for the "Card Usage Summary" panel. Because amount and
        description are encrypted TEXT they cannot be aggregated or searched in
        SQL; the rows are fetched and decrypted in Python (the same pattern as
        the dashboard metrics). Ordering and LIMIT stay in SQL,
        being done over plain columns.
        """
        from database.db import get_connection, SECRET_KEY
        from utils.crypto import decrypt

        conn = get_connection()
        try:
            cursor = conn.cursor()
            sql = (
                "SELECT amount, type, category, description, transaction_date"
                " FROM transactions WHERE account_id = ?"
                f" AND {COMPLETED_TX}"
                " ORDER BY transaction_date DESC, id DESC"
            )
            params = [int(account_id)]
            if limit is not None:
                parsed_limit = int(limit)
                if parsed_limit < 0:
                    raise ValueError("limit negatif olamaz")
                sql += " LIMIT ?"
                params.append(parsed_limit)
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        finally:
            conn.close()

        items = []
        for r in rows:
            try:
                amount = float(decrypt(str(r["amount"]), SECRET_KEY))
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception("[VERİ BÜTÜNLÜĞÜ] son işlem tutarı çözülemedi")
                amount = 0.0
            try:
                desc = decrypt(str(r["description"]), SECRET_KEY) or ""
            except KeyUnavailableError:
                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception("[VERİ BÜTÜNLÜĞÜ] son işlem açıklaması çözülemedi")
                desc = ""
            items.append({
                "amount": amount,
                "type": r["type"],
                "category": r["category"] or "",

                "description": desc.strip() or (r["category"] or "İşlem"),
                "date": (r["transaction_date"] or "")[:10],
            })
        return items
