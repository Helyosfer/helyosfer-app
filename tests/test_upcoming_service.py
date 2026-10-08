"""What is due soon: pending transactions and recurring payments within a week."""

import datetime
import os
import tempfile
import unittest
from unittest import mock

from tests.fixtures import AccountFixtureMixin

TODAY = datetime.date(2026, 3, 10)


class CollectUpcomingTest(AccountFixtureMixin, unittest.TestCase):
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

    def _recurring(self, name, due, automatic=True, kind="expense"):
        from database.db import insert_recurring_payment

        insert_recurring_payment(
            name, 100.0, "Ev Kirası", "monthly", due, automatic,
            account_id=self.account_id, transaction_type=kind,
        )

    def _collect(self):
        from services.upcoming_service import collect_upcoming

        return collect_upcoming(TODAY)

    def test_an_empty_profile_has_nothing_coming_up(self):
        self.assertEqual(self._collect(), [])

    def test_only_payments_due_within_a_week_or_overdue_are_listed(self):
        self._recurring("Gecikmis", "2026-03-05")
        self._recurring("Bugun", "2026-03-10")
        self._recurring("Sinirda", "2026-03-17")
        self._recurring("Uzak", "2026-03-18")
        names = [item["name"] for item in self._collect()]
        self.assertEqual(names, ["Gecikmis", "Bugun", "Sinirda"])

    def test_recurring_items_carry_amount_direction_and_how_they_are_paid(self):
        self._recurring("Kira", "2026-03-12", automatic=False)
        self._recurring("Maas", "2026-03-11", kind="income")
        salary, rent = self._collect()
        self.assertEqual((salary["name"], salary["income"], salary["automatic"]),
                         ("Maas", True, True))
        self.assertEqual((rent["name"], rent["income"], rent["automatic"]),
                         ("Kira", False, False))
        self.assertEqual(rent["amount"], 100.0)
        self.assertEqual(rent["kind"], "recurring")

    def test_pending_transactions_are_listed_however_far_ahead(self):
        from services.transaction_service import TransactionService

        future = (datetime.date.today() + datetime.timedelta(days=40)).isoformat()
        TransactionService.add_transaction(
            self.account_id, 250.0, "expense", "İnternet", "Fiber",
            transaction_date=f"{future} 10:00:00", detect_subscription=False,
        )
        items = self._collect()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "pending")
        self.assertEqual(items[0]["name"], "Fiber")
        self.assertEqual(items[0]["date"], future)
        self.assertEqual(items[0]["amount"], 250.0)


if __name__ == "__main__":
    unittest.main()
