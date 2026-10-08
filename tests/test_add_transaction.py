"""The date picker and status logic in the transaction dialog.

Scope:
  (a) A future-dated transaction is saved as `pending`, DOES NOT AFFECT the
      current balance, and lands in the pending list.
  (b) A past/today-dated transaction is saved as `completed` and the balance
      changes IMMEDIATELY.
  (c) The date button's label and the visibility of the future-date notice.
  (d) The `transaction_date` written is always in full timestamp form -- a
      date-only row breaks the time chart.

"""
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures import AccountFixtureMixin


class TransactionDateStatusTest(AccountFixtureMixin, unittest.TestCase):
    """The date -> status -> balance contract at the service level."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        from database.init_db import initialize_database
        initialize_database()
        self.account_id = self.create_test_account(balance=10000.0)

    def tearDown(self):
        self._patcher.stop()
        os.unlink(self.db_path)

    def _add_on(self, day_offset, amount=500.0, tx_type="expense"):
        """Adds a transaction in the timestamp format the dialog produces."""
        from services.transaction_service import TransactionService
        target = date.today() + timedelta(days=day_offset)
        stamp = (
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if day_offset == 0 else f"{target.isoformat()} 09:00:00"
        )
        TransactionService.add_transaction(
            account_id=self.account_id, amount=amount,
            transaction_type=tx_type, category="Süpermarket",
            description="Süpermarket", transaction_date=stamp,
            enforce_credit_limit=False,
        )
        return target

    def _balance(self):
        from services.account_service import AccountService
        return AccountService.get_account(self.account_id)["balance"]

    def _statuses(self):
        from database.db import get_connection
        conn = get_connection()
        try:
            return [r["status"] for r in conn.execute(
                "SELECT status FROM transactions ORDER BY id")]
        finally:
            conn.close()

    # ─── (a) Future date ─────────────────────────────────────────────────────

    def test_future_transaction_is_pending_and_balance_untouched(self):
        before = self._balance()
        self._add_on(day_offset=3)

        self.assertEqual(self._statuses(), ["pending"])
        self.assertAlmostEqual(self._balance(), before, places=2)

    def test_future_transaction_appears_in_pending_panel_source(self):
        from services.transaction_service import TransactionService
        target = self._add_on(day_offset=7, amount=1250.0)

        pending = TransactionService.get_pending_transactions()
        self.assertEqual(len(pending), 1)
        self.assertAlmostEqual(pending[0]["amount"], 1250.0, places=2)
        self.assertEqual(pending[0]["execution_date"], target.isoformat())

    def test_future_transaction_excluded_from_period_metrics(self):
        from services.transaction_service import TransactionService
        self._add_on(day_offset=5, amount=999.0)
        rows = TransactionService.get_transactions_by_period("Hayat Boyu")
        self.assertEqual(rows, [])


    def test_past_transaction_is_completed_and_deducted(self):
        before = self._balance()
        self._add_on(day_offset=-4, amount=750.0)

        self.assertEqual(self._statuses(), ["completed"])
        self.assertAlmostEqual(self._balance(), before - 750.0, places=2)

    def test_today_transaction_is_completed_and_deducted(self):
        before = self._balance()
        self._add_on(day_offset=0, amount=300.0)

        self.assertEqual(self._statuses(), ["completed"])
        self.assertAlmostEqual(self._balance(), before - 300.0, places=2)

    def test_past_transaction_does_not_enter_pending_panel(self):
        from services.transaction_service import TransactionService
        self._add_on(day_offset=-2)
        self.assertEqual(TransactionService.get_pending_transactions(), [])

    def test_past_income_increases_balance(self):
        before = self._balance()
        self._add_on(day_offset=-1, amount=2000.0, tx_type="income")
        self.assertAlmostEqual(self._balance(), before + 2000.0, places=2)


    def test_stored_dates_keep_full_timestamp_format(self):
        """A date-only row broke the time buckets in ui/charts.py."""
        from database.db import get_connection
        self._add_on(day_offset=-3)
        self._add_on(day_offset=0)
        self._add_on(day_offset=6)

        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT transaction_date FROM transactions").fetchall()
        finally:
            conn.close()

        self.assertEqual(len(rows), 3)
        for row in rows:
            with self.subTest(value=row["transaction_date"]):
                datetime.strptime(row["transaction_date"], "%Y-%m-%d %H:%M:%S")






if __name__ == "__main__":
    unittest.main()
