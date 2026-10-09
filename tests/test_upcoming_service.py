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

    def test_an_automatic_debt_installment_is_listed_when_its_pay_day_is_near(self):
        from database.db import insert_debt

        # Created today: the baseline is today's real month, so set what the
        # tests need by hand.
        def debt(name, day, last, auto=True):
            from database.db import get_connection

            insert_debt(name, 6000.0, 500.0, 12, int(auto), day)
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE active_debts SET last_auto_pay_date = ?"
                    " WHERE id = (SELECT MAX(id) FROM active_debts)", (last,))
                conn.commit()
            finally:
                conn.close()

        debt("Yakin", 15, "2026-02")
        debt("Uzak", 25, "2026-02")
        debt("Odendi", 5, "2026-03")
        debt("Gecikti", 31, "2026-01")
        debt("Elle", 12, None, auto=False)
        listed = {item["name"]: item for item in self._collect()}
        self.assertEqual(sorted(listed), ["Gecikti", "Yakin"])
        self.assertEqual(
            (listed["Yakin"]["kind"], listed["Yakin"]["date"], listed["Yakin"]["amount"],
             listed["Yakin"]["automatic"], listed["Yakin"]["income"]),
            ("debt", "2026-03-15", 500.0, True, False),
        )
        # The one that was missed is owed since the last day of February.
        self.assertEqual(listed["Gecikti"]["date"], "2026-02-28")

    def test_an_automatic_savings_contribution_is_listed_with_what_the_goal_needs(self):
        from database.db import get_connection
        from services.savings_auto_service import set_contribution
        from services.savings_service import SavingsService

        def plan(name, target, saved, amount, day, last):
            goal = SavingsService.create_goal(name, target, current_amount=saved)
            uid = next(g["goal_uid"] for g in SavingsService.get_goals() if g["id"] == goal)
            set_contribution(uid, self.account_id, amount, day)
            conn = get_connection()
            try:
                conn.execute(
                    "UPDATE savings_auto_contributions SET last_month = ? WHERE goal_uid = ?",
                    (last, uid))
                conn.commit()
            finally:
                conn.close()

        plan("Tatil", 10000.0, 0.0, 800.0, 12, "2026-02")
        plan("Az kaldi", 1000.0, 900.0, 800.0, 14, "2026-02")
        plan("Uzak", 10000.0, 0.0, 800.0, 28, "2026-02")
        plan("Bu ay tamam", 10000.0, 0.0, 800.0, 5, "2026-03")
        listed = [(item["name"], item["kind"], item["date"], item["amount"])
                  for item in self._collect()]
        self.assertEqual(listed, [
            ("Tatil", "saving", "2026-03-12", 800.0),
            ("Az kaldi", "saving", "2026-03-14", 100.0),
        ])

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
