"""Home screen headline figures, computed without an interface."""

import os
import tempfile
import unittest
from decimal import Decimal
from unittest import mock

from tests.fixtures import AccountFixtureMixin


class DashboardMetricsTest(AccountFixtureMixin, unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database

        initialize_database()
        self.account_id = self.create_test_account(balance=1000.0)

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _add(self, amount, tx_type):
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            self.account_id, amount, tx_type, "Market", "test",
            detect_subscription=False,
        )

    def _metrics(self, period="Bugün"):
        from services.dashboard_service import (
            compute_dashboard_metrics, invalidate_dashboard_cache,
        )

        invalidate_dashboard_cache()
        return compute_dashboard_metrics(period)

    def test_an_empty_profile_reports_the_account_balance_and_no_flow(self):
        metrics = self._metrics()
        self.assertEqual(metrics["total_balance"], Decimal("1000"))
        self.assertEqual(metrics["period_income"], 0)
        self.assertEqual(metrics["period_expense"], 0)

    def test_todays_transactions_enter_the_period_and_the_balance(self):
        self._add(250.0, "income")
        self._add(100.0, "expense")
        metrics = self._metrics()
        self.assertEqual(metrics["period_income"], Decimal("250"))
        self.assertEqual(metrics["period_expense"], Decimal("100"))
        self.assertEqual(metrics["period_net"], Decimal("150"))
        self.assertEqual(metrics["total_balance"], Decimal("1150"))

    def test_the_result_is_reused_until_the_data_changes(self):
        from services.dashboard_service import compute_dashboard_metrics

        first = self._metrics()
        self.assertIs(compute_dashboard_metrics("Bugün"), first)
        self._add(10.0, "expense")
        self.assertIsNot(compute_dashboard_metrics("Bugün"), first)


if __name__ == "__main__":
    unittest.main()
