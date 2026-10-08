"""Wallet (the home screen total) <-> My Cards (account balances) synchronisation.

THE BUG: when an account was added with an opening
balance, the amount appeared under "My Cards" (accounts.balance) but not in
the "My Wallet" total on the home screen. The home screen total was fed only
from the transaction ledger (income - expense); the opening balance, however,
was written not to transactions but to accounts.balance +
balance_events('account_opened').

The fix: DashboardService.get_opening_baseline() returns the opening base as a
separate quantity and adds it to the home screen total. So accounts +
transactions combine into a single truth.

"""
import os
import tempfile
import unittest
from unittest import mock



class WalletSyncTest(unittest.TestCase):
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

    def _transaction_cashflow(self):
        """The same as what the home screen uses: the income-minus-expense of completed transactions."""
        from database.db import COMPLETED_TX, get_connection, SECRET_KEY
        from utils.crypto import decrypt

        conn = get_connection()
        try:
            rows = conn.execute(
                f"SELECT amount, type FROM transactions WHERE {COMPLETED_TX}"
            ).fetchall()
        finally:
            conn.close()
        total = 0.0
        for amount, t_type in rows:
            try:
                value = float(decrypt(str(amount), SECRET_KEY))
            except Exception:
                value = 0.0
            if t_type in ("income", "Gelir"):
                total += value
            elif t_type in ("expense", "Gider"):
                total -= value
        return round(total, 2)

    def test_initial_balance_appears_in_opening_baseline(self):
        """THE REAL BUG: the opening balance must reach the wallet (with no transaction in the ledger)."""
        from services.account_service import AccountService
        from services.queries import DashboardService

        AccountService.create_account(
            "Nakit Cüzdanım", "checking", initial_balance=5000
        )

        self.assertEqual(self._transaction_cashflow(), 0.0)
        self.assertEqual(DashboardService.get_opening_baseline(), 5000.0)

        home_total = self._transaction_cashflow() + DashboardService.get_opening_baseline()
        self.assertEqual(home_total, DashboardService.get_total_balance())

    def test_credit_card_debt_reduces_baseline(self):
        """A credit card's opening debt enters signed; the base decreases by the debt amount."""
        from services.account_service import AccountService
        from services.queries import DashboardService

        AccountService.create_account(
            "Kart", "credit_card", initial_balance=1000, credit_limit=5000
        )
        self.assertEqual(DashboardService.get_opening_baseline(), -1000.0)

    def test_home_total_matches_net_worth_after_transactions(self):
        """In an account-plus-transaction scenario, the home total must equal net worth."""
        from services.account_service import AccountService
        from services.transaction_service import TransactionService
        from services.queries import DashboardService

        account_id = AccountService.create_account(
            "Nakit", "checking", initial_balance=5000
        )
        TransactionService.add_transaction(
            account_id=account_id, amount=1000, transaction_type="income",
            category="Maaş", description="maaş",
        )
        TransactionService.add_transaction(
            account_id=account_id, amount=300, transaction_type="expense",
            category="Market", description="market",
        )

        home_total = self._transaction_cashflow() + DashboardService.get_opening_baseline()
        self.assertEqual(home_total, 5700.0)
        self.assertEqual(home_total, DashboardService.get_total_balance())
        self.assertEqual(home_total, AccountService.get_net_worth()["net"])

    def test_deleting_card_removes_its_baseline(self):
        """When a card is deleted its opening base must drop too (no orphan base left behind).

        Because the deletion path also clears balance_events, using the ledger
        base rather than a synthetic opening transaction leaves no
        double-counting after the deletion -- this is the invariant this test
        protects.
        """
        from services.account_service import AccountService
        from services.queries import DashboardService

        card_id = AccountService.create_account(
            "Geçici Kart", "credit_card", initial_balance=1000, credit_limit=5000
        )
        self.assertEqual(DashboardService.get_opening_baseline(), -1000.0)
        AccountService.delete_credit_card(card_id)
        self.assertEqual(DashboardService.get_opening_baseline(), 0.0)


if __name__ == "__main__":
    unittest.main()
