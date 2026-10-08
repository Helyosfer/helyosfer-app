"""The record-integrity and amount-boundary contracts of a recurring charge.

The tests here measure THREE separate contracts of
`process_due_recurring_payment` and the writes feeding it:

  1. The marker must be TRACEABLE:
     `recurring_operation_markers.transaction_id` must really point at that
     charge's `transactions.id`. The column is READ FROM NOWHERE today, so a
     wrong value shows the user nothing -- but this column's only job is to
     point at the source, and a wrong source misleads the first reader (support,
     an export, a future "cancel this charge" flow) to the wrong row. The worst
     kind of silent error.
  2. THE AMOUNT BOUNDARY: a non-finite/non-positive amount can never enter
     PERSISTENTLY through any write path. The interface cannot produce these
     already; what is measured here is the service boundary itself.
  3. THE DECISION AND THE WRITE ON THE SAME TRANSACTION: the spending
     permission must be asked from the cursor the write is holding -- not with
     `check_spending_allowed`, which opens a separate connection (that
     function's own contract forbids it).

"""
import math
import os
import sqlite3
import tempfile
import unittest
from datetime import date
from unittest import mock

from tests.fixtures import AccountFixtureMixin
from tests.test_connection_ownership_contract import connection_ledger


class RecurringChargeIntegrityTest(AccountFixtureMixin, unittest.TestCase):

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self.addCleanup(lambda: os.path.exists(self.db_path) and os.unlink(self.db_path))

        from database.init_db import initialize_database
        initialize_database()
        self.account_id = self.create_test_account("Vadesiz", balance=10000.0)


    def _add(self, name="Netflix", amount=149.99, **kwargs):
        from database.db import (
            get_active_recurring_payments, insert_recurring_payment,
        )
        insert_recurring_payment(
            name, amount, "Dijital Platformlar", "monthly",
            date.today().isoformat(), auto_deduct=0,
            account_id=self.account_id, recurrence_day=date.today().day,
            **kwargs,
        )
        return next(
            p for p in get_active_recurring_payments() if p["name"] == name
        )

    def _rows(self, sql, *params):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            return [dict(row) for row in conn.execute(sql, params)]
        finally:
            conn.close()

    def _counts(self):
        return {
            table: self._rows(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]
            for table in ("transactions", "balance_events",
                          "recurring_payments", "recurring_operation_markers")
        }


    def test_marker_records_the_transaction_it_charged(self):
        """The row the marker points at must REALLY be that charge's transaction.

        Before the fix, `balance_events.id` was written here: `lastrowid`
        belongs to the cursor, and `adjust_account_balance` INSERTs the ledger
        row with the same cursor, so by the time the marker was reached the
        value had already changed.
        """
        from database.db import process_due_recurring_payment

        payment = self._add()
        self.assertTrue(process_due_recurring_payment(payment))

        transactions = self._rows("SELECT id FROM transactions ORDER BY id")
        markers = self._rows("SELECT * FROM recurring_operation_markers")
        self.assertEqual(len(transactions), 1)
        self.assertEqual(len(markers), 1)
        self.assertEqual(
            markers[0]["transaction_id"], transactions[0]["id"],
            "marker gerçek transactions.id'yi göstermiyor",
        )

    def test_balance_event_and_marker_point_at_the_same_transaction(self):
        """The ledger row and the marker must point at THE SAME transaction -- a single truth."""
        from database.db import process_due_recurring_payment

        payment = self._add()
        process_due_recurring_payment(payment)

        transaction_id = self._rows("SELECT id FROM transactions")[0]["id"]
        event = self._rows(
            "SELECT ref_id FROM balance_events WHERE source='recurring_payment'"
        )[0]
        marker = self._rows("SELECT * FROM recurring_operation_markers")[0]
        self.assertEqual(event["ref_id"], transaction_id)
        self.assertEqual(marker["transaction_id"], transaction_id)

    def test_second_pass_over_the_same_due_date_changes_nothing(self):
        """Idempotency: processing the same due date a second time changes neither the charge nor the marker."""
        from database.db import process_due_recurring_payment

        payment = self._add()
        self.assertTrue(process_due_recurring_payment(payment))
        after_first = (self._counts(),
                       self._rows("SELECT * FROM recurring_operation_markers"))


        self.assertFalse(process_due_recurring_payment(payment))
        self.assertEqual(
            (self._counts(),
             self._rows("SELECT * FROM recurring_operation_markers")),
            after_first,
            "ikinci geçiş kalıcı durumu değiştirdi",
        )


    def test_insert_rejects_non_finite_and_non_positive_amounts(self):
        from database.db import insert_recurring_payment

        before = self._counts()
        for amount in (float("nan"), float("inf"), float("-inf"),
                       "nan", "inf", "-inf", 0, -5.0, "abc"):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    insert_recurring_payment(
                        f"Kötü {amount!r}", amount, "Dijital", "monthly",
                        date.today().isoformat(), auto_deduct=0,
                        account_id=self.account_id,
                        recurrence_day=date.today().day,
                    )
        self.assertEqual(self._counts(), before, "geçersiz tutar satır yazdı")

    def test_subscription_amount_update_rejects_non_finite_amounts(self):
        from services.recurring_service import update_subscription_amount

        payment = self._add(amount=100.0)
        for amount in (float("nan"), float("inf"), float("-inf"),
                       "nan", "inf", 0, -1.0):
            with self.subTest(amount=amount):
                with self.assertRaises(ValueError):
                    update_subscription_amount(payment["id"], amount)

        from database.db import get_active_recurring_payments
        current = get_active_recurring_payments()[0]
        self.assertEqual(current["amount"], 100.0,
                         "reddedilen güncelleme yine de tutarı değiştirdi")

    def test_stored_amount_is_the_amount_that_will_be_charged(self):
        """The stored amount is the amount that will be charged -- the two are not rounded separately."""
        from database.db import (
            get_active_recurring_payments, process_due_recurring_payment,
        )

        payment = self._add(name="Kuruşlu", amount=149.994)
        self.assertEqual(get_active_recurring_payments()[0]["amount"], 149.99)

        process_due_recurring_payment(payment)
        from services.account_service import AccountService
        self.assertEqual(
            AccountService.get_account(self.account_id)["balance"],
            10000.0 - 149.99,
        )

    def test_a_pre_existing_non_finite_row_is_reported_as_invalid(self):
        """`nan` left by an old structure must not be counted as VALID on the read path.

        The flag exists exactly to protect the aggregate field (the budget
        reserve); because `float("nan")` raises no exception it used to return
        `True`, and the monthly budget broke with a generic `ValueError`.
        """
        from database.db import SECRET_KEY, get_active_recurring_payments
        from utils.crypto import encrypt
        from utils.errors import FinancialDataIntegrityError

        self._add(name="Bozuk", amount=10.0)
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE recurring_payments SET amount = ?",
                (encrypt("nan", SECRET_KEY),),
            )
            conn.commit()
        finally:
            conn.close()

        payment = get_active_recurring_payments()[0]
        self.assertFalse(payment["amount_is_valid"])
        self.assertTrue(math.isfinite(payment["amount"]))

        from services.budget_service import get_reserved_recurring_items
        with self.assertRaises(FinancialDataIntegrityError):
            get_reserved_recurring_items(date.today().month, date.today().year)

    def test_a_pre_existing_non_positive_row_is_reported_as_invalid(self):
        """Zero and negative old records are INVALID too -- and that was the silent one.

        `recurring_payments.amount` is a MAGNITUDE; direction is carried in the
        `transaction_type` column. A negative amount is therefore not "a
        reversed payment" but an invalid record, and all three write paths
        reject it. The read path, however, caught the non-finite case while
        letting the negative one through: a row of -10.00 entered the monthly
        budget as a -10.00 reserve and showed the spendable amount 10 lira TOO
        HIGH (measured). Non-finiteness broke loudly; the negative produced a
        SILENT wrong total.

        The data is not corrected: no `abs()` is taken and the row is not
        updated.
        """
        from database.db import SECRET_KEY, get_active_recurring_payments
        from utils.crypto import decrypt, encrypt
        from utils.errors import FinancialDataIntegrityError
        from services.budget_service import calculate_monthly_budget

        for stored in ("-10", "0", "0.0", "-0.004"):
            with self.subTest(stored=stored):
                self._add(name=f"Legacy {stored}", amount=10.0)
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.execute(
                        "UPDATE recurring_payments SET amount = ?"
                        " WHERE id = (SELECT MAX(id) FROM recurring_payments)",
                        (encrypt(stored, SECRET_KEY),),
                    )
                    conn.commit()
                finally:
                    conn.close()

                payments = get_active_recurring_payments()
                self.assertFalse(
                    payments[-1]["amount_is_valid"],
                    f"{stored!r} geçerli tutar sayıldı",
                )
                with self.assertRaises(FinancialDataIntegrityError):
                    calculate_monthly_budget(
                        date.today().month, date.today().year)


                conn = sqlite3.connect(self.db_path)
                try:
                    raw = conn.execute(
                        "SELECT amount FROM recurring_payments"
                        " WHERE id = (SELECT MAX(id) FROM recurring_payments)"
                    ).fetchone()[0]
                    conn.execute(
                        "DELETE FROM recurring_payments"
                        " WHERE id = (SELECT MAX(id) FROM recurring_payments)")
                    conn.commit()
                finally:
                    conn.close()
                self.assertEqual(decrypt(raw, SECRET_KEY), stored)


    def test_refund_rejects_a_corrupted_charge_without_touching_money(self):
        """If the STORED amount of the charge to be refunded is corrupt, nothing is written.

        Measured result with `inf`: the refund was COMMITTED and the account
        balance became `inf` permanently (the transaction row, the ledger row
        and the marker included). With `nan` it hit `balance_events.delta`'s NOT
        NULL constraint and came out as a raw `sqlite3.IntegrityError`. A
        negative or zero amount was silently counted as "no charge this
        month".
        """
        from database.db import SECRET_KEY, process_due_recurring_payment
        from services.recurring_service import refund_current_period_charge
        from utils.crypto import encrypt
        from utils.errors import FinancialDataIntegrityError

        for stored in ("nan", "inf", "-inf", "-50.0", "0.0"):
            with self.subTest(stored=stored):
                self.setUp()
                payment = self._add(amount=100.0)
                process_due_recurring_payment(payment)

                conn = sqlite3.connect(self.db_path)
                try:
                    conn.execute(
                        "UPDATE transactions SET amount = ? WHERE type='expense'",
                        (encrypt(stored, SECRET_KEY),),
                    )
                    conn.commit()
                finally:
                    conn.close()

                before = self._counts()
                balance_before = self._rows(
                    "SELECT balance FROM accounts WHERE id=?",
                    self.account_id)[0]["balance"]

                with self.assertRaises(FinancialDataIntegrityError):
                    refund_current_period_charge(payment["id"])

                self.assertEqual(self._counts(), before,
                                 "bozuk tahsilat için iade satırı yazıldı")
                self.assertEqual(
                    self._rows("SELECT balance FROM accounts WHERE id=?",
                               self.account_id)[0]["balance"],
                    balance_before,
                    "bozuk tahsilat bakiyeyi değiştirdi",
                )

    def test_healthy_refund_still_works_and_stays_idempotent(self):
        from database.db import process_due_recurring_payment
        from services.recurring_service import refund_current_period_charge
        from services.account_service import AccountService

        payment = self._add(amount=100.0)
        process_due_recurring_payment(payment)
        self.assertEqual(
            AccountService.get_account(self.account_id)["balance"],
            10000.0 - 100.0)

        self.assertEqual(refund_current_period_charge(payment["id"]), 100.0)
        after_first = self._counts()
        self.assertEqual(
            AccountService.get_account(self.account_id)["balance"], 10000.0)


        self.assertEqual(refund_current_period_charge(payment["id"]), 0.0)
        self.assertEqual(self._counts(), after_first)
        self.assertEqual(
            AccountService.get_account(self.account_id)["balance"], 10000.0)


    def test_charge_decides_and_writes_on_a_single_connection(self):
        """The spending permission must NOT be asked from a separate connection.

        `check_spending_allowed` opens its own connection and its docstring
        explicitly forbids using it on the write path; `transaction_service` and
        `asset_purchase_service` had already moved the decision onto the
        caller's cursor. This test makes that contract measurable: the charge
        opens a SINGLE connection.
        """
        from database.db import process_due_recurring_payment

        payment = self._add()
        with connection_ledger() as ledger:
            process_due_recurring_payment(payment)
        self.assertEqual(
            len(ledger.opened), 1,
            "tahsilat yazma kilidini tutarken ikinci bir bağlantı açtı",
        )
        self.assertEqual(ledger.leaked, [])

    def test_credit_limit_is_enforced_from_inside_the_write_lock(self):
        from database.db import process_due_recurring_payment
        from services.account_service import AccountService

        card_id = AccountService.create_account(
            "Kart", "credit_card", initial_balance=0, credit_limit=100.0,
        )
        payment = self._add(name="Pahalı abonelik", amount=150.0)
        payment = dict(payment, account_id=card_id)

        before = self._counts()
        with self.assertRaisesRegex(ValueError, "Limit yetersiz"):
            process_due_recurring_payment(payment)
        self.assertEqual(self._counts(), before,
                         "reddedilen tahsilattan parçalı kayıt kaldı")
        self.assertEqual(AccountService.get_account(card_id)["debt"], 0.0)

    def test_frozen_account_still_blocks_the_charge(self):
        from database.db import process_due_recurring_payment

        payment = self._add()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("UPDATE accounts SET is_frozen = 1 WHERE id = ?",
                         (self.account_id,))
            conn.commit()
        finally:
            conn.close()

        before = self._counts()
        with self.assertRaises(ValueError):
            process_due_recurring_payment(payment)
        self.assertEqual(self._counts(), before)


if __name__ == "__main__":
    unittest.main()
