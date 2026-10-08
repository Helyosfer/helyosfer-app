"""Tests of the ownerless-transaction guard and the onboarding routing.

CONTEXT: `initialize_database()` used to open three default accounts (Nakit
2500 / Banka 15000 / Kredi Kartı -3500). Because the user saw a balance they
had not added, the seed was removed. But `DEFAULT_ACCOUNT_ID = 1` was still
used at 24 call sites: on a fresh installation id=1 matches no row,
`UPDATE accounts ... WHERE id = 1` silently affects 0 rows, and the money went
nowhere.

The tests here lock two defences:
  1. An attempt to write to a non-existent account DOES NOT STAY SILENT; it
     raises ValueError and leaves no half record (atomicity).
  2. With no account at all the user is routed to onboarding rather than the
     dashboard.

"""
import os
import tempfile
import unittest
from unittest import mock

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.fixtures import AccountFixtureMixin


class OrphanTransactionGuardTest(AccountFixtureMixin, unittest.TestCase):

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

    def _count(self, table):
        from database.db import get_connection
        conn = get_connection()
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()

    def test_fresh_database_has_no_seed_accounts(self):
        """The contract: a fresh installation produces no balance that does not belong to the user."""
        self.assertEqual(self._count("accounts"), 0)

    def test_transaction_to_missing_account_raises(self):
        from services.transaction_service import TransactionService
        with self.assertRaises(ValueError) as ctx:
            TransactionService.add_transaction(
                account_id=1, amount=100.0, transaction_type="income",
                category="Maaş", description="sahipsiz",
                enforce_credit_limit=False,
            )
        self.assertIn("Hesap bulunamadı", str(ctx.exception))

    def test_failed_transaction_leaves_no_orphan_row(self):
        """This was the real bug: the transaction was written and the balance was not updated."""
        from services.transaction_service import TransactionService
        with self.assertRaises(ValueError):
            TransactionService.add_transaction(
                account_id=1, amount=100.0, transaction_type="income",
                category="Maaş", description="sahipsiz",
                enforce_credit_limit=False,
            )
        self.assertEqual(self._count("transactions"), 0)

    def test_future_dated_transaction_also_guarded(self):
        """The pending path does not call adjust_account_balance; it must be guarded separately."""
        from datetime import date, timedelta
        from services.transaction_service import TransactionService
        future = (date.today() + timedelta(days=5)).isoformat()
        with self.assertRaises(ValueError):
            TransactionService.add_transaction(
                account_id=1, amount=100.0, transaction_type="income",
                category="Maaş", description="ileri tarihli sahipsiz",
                transaction_date=f"{future} 09:00:00",
                enforce_credit_limit=False,
            )
        self.assertEqual(self._count("transactions"), 0)

    def test_adjust_balance_raises_for_missing_account(self):
        """The single choke point of balance mutation must be guarded on its own too."""
        from database.db import adjust_account_balance, get_connection
        conn = get_connection()
        try:
            with self.assertRaises(ValueError):
                adjust_account_balance(conn.cursor(), 999, "income", 50.0)
        finally:
            conn.close()

    def test_transaction_succeeds_once_account_exists(self):
        from services.transaction_service import TransactionService
        from services.account_service import AccountService
        account_id = self.create_test_account(balance=0.0)

        TransactionService.add_transaction(
            account_id=account_id, amount=250.0, transaction_type="income",
            category="Maaş", description="gerçek hesap",
            enforce_credit_limit=False,
        )
        self.assertEqual(self._count("transactions"), 1)
        self.assertAlmostEqual(
            AccountService.get_account(account_id)["balance"], 250.0, places=2)


class OnboardingRoutingTest(AccountFixtureMixin, unittest.TestCase):

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

    def test_has_any_account_reflects_state(self):
        from services.account_service import AccountService
        self.assertFalse(AccountService.has_any_account())
        self.create_test_account()
        self.assertTrue(AccountService.has_any_account())

    def test_account_exists_is_precise(self):
        from services.account_service import AccountService
        account_id = self.create_test_account()
        self.assertTrue(AccountService.account_exists(account_id))
        self.assertFalse(AccountService.account_exists(account_id + 999))




if __name__ == "__main__":
    unittest.main()
