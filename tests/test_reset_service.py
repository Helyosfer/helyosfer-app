"""A full reset returns the profile to its first-run state."""

import os
import tempfile
import unittest
from unittest import mock

from tests.fixtures import AccountFixtureMixin
from utils.config_store import ConfigStore


class ResetAllDataTest(AccountFixtureMixin, unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.db_path = os.path.join(self._tmp.name, "finance.db")
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        from database.init_db import initialize_database

        initialize_database()
        self.store = ConfigStore(os.path.join(self._tmp.name, "config.json"))

    def _counts(self):
        from database.db import managed_connection

        with managed_connection() as conn:
            return {
                table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("accounts", "transactions", "active_debts",
                              "recurring_payments", "balance_events", "categories")
            }

    def test_everything_the_user_entered_is_erased(self):
        from database.db import insert_recurring_payment
        from services.debt_payment_service import DebtPaymentService
        from services.reset_service import reset_all_data
        from services.transaction_service import TransactionService

        account_id = self.create_test_account(balance=5000.0)
        TransactionService.add_transaction(
            account_id, 100.0, "expense", "Süpermarket", "x", detect_subscription=False
        )
        DebtPaymentService.create_debt("Telefon", 100.0, 3)
        insert_recurring_payment(
            "Kira", 10.0, "Ev Kirası", "monthly", "2026-01-01", False,
            account_id=account_id,
        )
        self.store.put("security", pin_hash="h", salt="s", is_set=True)
        self.store.put("security_throttle", failed_attempts=9, last_failed_at=1.0)
        self.store.put("display", style="Light")

        reset_all_data(self.store)

        counts = self._counts()
        for table in ("accounts", "transactions", "active_debts",
                      "recurring_payments", "balance_events"):
            self.assertEqual(counts[table], 0, table)
        self.assertGreater(counts["categories"], 0)
        self.assertFalse(self.store.exists("security"))
        self.assertFalse(self.store.exists("security_throttle"))
        self.assertEqual(self.store.get("display"), {"style": "Light"})

    def test_ids_start_again_from_one(self):
        from services.reset_service import reset_all_data

        self.create_test_account(balance=1.0)
        self.create_test_account(balance=2.0)
        reset_all_data(self.store)
        self.assertEqual(self.create_test_account(balance=3.0), 1)

    def test_the_wipe_survives_enforced_foreign_keys(self):
        from services.reset_service import reset_all_data
        from services.transaction_service import TransactionService

        account_id = self.create_test_account(balance=50.0)
        for _ in range(3):
            TransactionService.add_transaction(
                account_id, 1.0, "expense", "Süpermarket", "x",
                detect_subscription=False,
            )
        reset_all_data(self.store)
        self.assertEqual(self._counts()["transactions"], 0)


if __name__ == "__main__":
    unittest.main()
