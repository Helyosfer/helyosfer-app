"""Tests of get_opening_baseline_by_period.

CONTEXT: a user with a single newly opened account (who had entered no
transaction yet) saw "No Data" on the pie/line chart of the My Assets tab --
because the opening balance is never written to the `transactions` table. This
function returns the opening balance as a SEPARATE "Opening Balance" slice; it
DOES NOT WRITE a real income transaction, so other analyses such as the savings
rate and the health score are unaffected (see
DashboardService.get_opening_baseline, the same principle).

"""
import os
import tempfile
import unittest
from unittest import mock


class OpeningBaselinePeriodTestCase(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()
        from database.init_db import initialize_database
        initialize_database()

    def tearDown(self):
        self._patcher.stop()
        os.unlink(self.db_path)

    def _retime_last_event(self, days_ago):
        from database.db import get_connection
        conn = get_connection()
        conn.execute(
            "UPDATE balance_events SET ts = datetime('now', ?) "
            "WHERE id = (SELECT MAX(id) FROM balance_events)",
            (f"-{days_ago} days",),
        )
        conn.commit()
        conn.close()

    def test_today_includes_account_opened_today(self):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        AccountService.create_account(
            "Nakit Cüzdanım", "checking", initial_balance=22500
        )
        self.assertEqual(
            TransactionService.get_opening_baseline_by_period("Bugün"), 22500.0
        )

    def test_account_opened_days_ago_excluded_from_today(self):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        AccountService.create_account(
            "Eski Hesap", "checking", initial_balance=5000
        )
        self._retime_last_event(days_ago=10)
        self.assertEqual(
            TransactionService.get_opening_baseline_by_period("Bugün"), 0.0
        )

    def test_lifetime_includes_account_opened_in_the_past(self):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        AccountService.create_account(
            "Eski Hesap", "checking", initial_balance=5000
        )
        self._retime_last_event(days_ago=400)
        self.assertEqual(
            TransactionService.get_opening_baseline_by_period("Hayat Boyu"),
            5000.0,
        )

    def test_credit_card_opening_debt_is_excluded(self):
        """A credit card's opening DEBT (a negative delta) must not leak into the income slice."""
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        AccountService.create_account(
            "Kart", "credit_card", initial_balance=1000, credit_limit=5000
        )
        self.assertEqual(
            TransactionService.get_opening_baseline_by_period("Bugün"), 0.0
        )

    def test_multiple_accounts_sum_together(self):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        AccountService.create_account(
            "Nakit", "checking", initial_balance=1000
        )
        AccountService.create_account(
            "Banka", "checking", initial_balance=2500
        )
        self.assertEqual(
            TransactionService.get_opening_baseline_by_period("Bugün"), 3500.0
        )


if __name__ == "__main__":
    unittest.main()
