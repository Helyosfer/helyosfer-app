"""Atomic automatic debt installment settlement."""
from datetime import datetime
from database.db import SECRET_KEY, adjust_account_balance, get_connection
from utils.crypto import decrypt, encrypt
from utils.financial_decimal import fiat


class DebtPaymentService:
    @staticmethod
    def pay_auto(debt_id, account_id, installments, month, _fault_hook=None, paid_on=None):
        """Takes `installments` for `month`; never twice for the same month.

        `paid_on` is the day the instalment was due. When that day has
        passed, the record and the ledger carry it instead of today.
        """
        conn = get_connection()
        try:
            with conn:
                cur = conn.cursor(); cur.execute("BEGIN IMMEDIATE")
                row = cur.execute("SELECT * FROM active_debts WHERE id=? AND is_active=1", (debt_id,)).fetchone()
                if row is None or row["last_auto_pay_date"] == month:
                    return False
                remaining = row["total_installments"] - row["paid_installments"]
                count = min(int(installments), remaining)
                if count <= 0: return False
                amount = float(fiat(decrypt(row["monthly_payment"], SECRET_KEY)) * count)
                desc = decrypt(row["debt_name"], SECRET_KEY) + " (Otomatik Taksit Ödemesi)"
                moment = datetime.now()
                now = moment.strftime("%Y-%m-%d %H:%M:%S")
                late = paid_on is not None and paid_on.isoformat() < now[:10]
                if late:
                    now = f"{paid_on.isoformat()} {moment.strftime('%H:%M:%S')}"
                cur.execute("INSERT INTO transactions (account_id,amount,type,category,description,transaction_date) VALUES (?,?,'expense','Kredi Taksiti',?,?)", (account_id, encrypt(str(amount), SECRET_KEY), encrypt(desc, SECRET_KEY), now))


                transaction_id = cur.lastrowid
                if _fault_hook: _fault_hook("after_transaction")
                adjust_account_balance(
                    cur, account_id, "expense", amount, ref_id=transaction_id,
                    source="debt_payment", effective_at=now if late else None,
                )
                if _fault_hook: _fault_hook("after_balance")
                paid = row["paid_installments"] + count
                cur.execute("UPDATE active_debts SET paid_installments=?, last_auto_pay_date=?, is_active=? WHERE id=?", (paid, month, 0 if paid >= row["total_installments"] else 1, debt_id))
                if _fault_hook: _fault_hook("before_commit")
            return True
        finally:
            conn.close()

    @staticmethod
    def pay_manual(debt_id, account_id, installments=None):
        """Pays instalments the user chose, from the account the user chose.

        The debt's progress, the expense transaction and the balance change
        are written in ONE commit: a crash can never leave an instalment
        marked paid with no money taken, or the reverse. `installments=None`
        closes the debt by paying everything that remains.

        Returns the amount paid. Raises ValueError if the debt is not active,
        the count is out of range, or the account may not be spent from.
        """
        from services.account_service import AccountService

        conn = get_connection()
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("BEGIN IMMEDIATE")
                row = cur.execute(
                    "SELECT * FROM active_debts WHERE id=? AND is_active=1", (debt_id,)
                ).fetchone()
                if row is None:
                    raise ValueError("Bu borç zaten tamamen ödenmiş!")
                remaining = row["total_installments"] - row["paid_installments"]
                if remaining <= 0:
                    raise ValueError("Bu borç zaten tamamen ödenmiş!")
                closing = installments is None
                count = remaining if closing else int(installments)
                if not 1 <= count <= remaining:
                    raise ValueError("Taksit sayısı kalan taksit sayısını aşamaz.")

                amount = float(fiat(decrypt(row["monthly_payment"], SECRET_KEY)) * count)
                name = decrypt(row["debt_name"], SECRET_KEY)
                AccountService.assert_spending_allowed(cur, account_id, amount, "expense")
                if closing:
                    category, desc = "Borç Ödeme", f"{name} (Tamamen Kapatma)"
                else:
                    category, desc = "Kredi Taksiti", f"{name} ({count} Taksit Ödemesi)"
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute(
                    "INSERT INTO transactions (account_id,amount,type,category,description,transaction_date)"
                    " VALUES (?,?,'expense',?,?,?)",
                    (account_id, encrypt(str(amount), SECRET_KEY), category,
                     encrypt(desc, SECRET_KEY), now),
                )
                adjust_account_balance(
                    cur, account_id, "expense", amount,
                    ref_id=cur.lastrowid, source="debt_payment",
                )
                paid = row["paid_installments"] + count
                cur.execute(
                    "UPDATE active_debts SET paid_installments=?, is_active=? WHERE id=?",
                    (paid, 0 if paid >= row["total_installments"] else 1, debt_id),
                )
            return amount
        finally:
            conn.close()

    @staticmethod
    def create_debt(name, monthly_payment, installments, auto_pay=False, auto_pay_day=1,
                    auto_pay_account_id=None):
        """Records an instalment debt.

        The total is derived from the ROUNDED instalment times the count, so
        it is exactly what the monthly payments will add up to.
        """
        from database.db import insert_debt

        name = (name or "").strip()
        if not name:
            raise ValueError("Borç adı boş olamaz.")
        monthly = fiat(monthly_payment)
        if monthly <= 0:
            raise ValueError("Aylık taksit 0'dan büyük olmalıdır.")
        count = int(installments)
        if not 1 <= count <= 600:
            raise ValueError("Taksit sayısı 1 ile 600 arasında olmalıdır.")
        day = int(auto_pay_day or 1)
        if not 1 <= day <= 31:
            raise ValueError("Ödeme günü 1 ile 31 arasında olmalıdır.")
        insert_debt(
            name, monthly * count, monthly, count, int(bool(auto_pay)), day,
            auto_pay_account_id if auto_pay else None,
        )
