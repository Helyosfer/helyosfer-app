"""A monthly contribution to a savings goal moves once, carefully."""

import datetime
import os
import tempfile
import unittest
from unittest import mock


class SavingsAutoServiceTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 10000.0)
        goal_id = SavingsService.create_goal("Holiday", 3000.0)
        self.goal = next(g for g in SavingsService.get_goals() if g["id"] == goal_id)
        self.uid = self.goal["goal_uid"]

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _state(self):
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        goal = next(g for g in SavingsService.get_goals() if g["goal_uid"] == self.uid)
        return AccountService.get_account(self.account)["balance"], goal["current_amount"]

    def _run(self, year, month, day):
        from services.savings_auto_service import process_due_contributions

        return process_due_contributions(datetime.date(year, month, day))

    def _plan(self, amount=500.0, day=10, account=None):
        from services.savings_auto_service import set_contribution

        set_contribution(self.uid, account or self.account, amount, day)

    # -- when it moves -------------------------------------------------------
    def test_nothing_moves_before_its_day(self):
        self._plan()
        self.assertEqual(self._run(2026, 3, 9), 0)
        self.assertEqual(self._state(), (10000.0, 0.0))

    def test_it_moves_once_on_or_after_its_day(self):
        self._plan()
        self.assertEqual(self._run(2026, 3, 10), 1)
        self.assertEqual(self._state(), (9500.0, 500.0))
        self.assertEqual(self._run(2026, 3, 25), 0)
        self.assertEqual(self._state(), (9500.0, 500.0))
        self.assertEqual(self._run(2026, 4, 12), 1)
        self.assertEqual(self._state(), (9000.0, 1000.0))

    def test_missed_months_are_not_made_up_for(self):
        self._plan()
        self._run(2026, 3, 10)
        self.assertEqual(self._run(2026, 7, 20), 1)
        self.assertEqual(self._state(), (9000.0, 1000.0))

    def test_day_31_falls_on_the_last_day_of_a_shorter_month(self):
        self._plan(day=31)
        self.assertEqual(self._run(2026, 2, 27), 0)
        self.assertEqual(self._run(2026, 2, 28), 1)

    # -- care with the money ---------------------------------------------------
    def test_it_never_moves_more_than_the_goal_needs(self):
        self._plan(amount=2000.0)
        self._run(2026, 3, 10)
        self.assertEqual(self._run(2026, 4, 10), 1)
        self.assertEqual(self._state(), (7000.0, 3000.0))
        # The goal is complete, so the plan is gone and nothing more moves.
        from services.savings_auto_service import get_contributions

        self.assertEqual(self._run(2026, 5, 10), 0)
        self.assertEqual(get_contributions(), {})
        self.assertEqual(self._state(), (7000.0, 3000.0))

    def test_an_account_that_cannot_cover_it_is_left_alone_and_tried_again(self):
        from services.transaction_service import TransactionService

        self._plan(amount=500.0)
        TransactionService.add_transaction(
            self.account, 9800.0, "expense", "Taksi", "x", detect_subscription=False)
        self.assertEqual(self._run(2026, 3, 10), 0)
        self.assertEqual(self._state(), (200.0, 0.0))
        TransactionService.add_transaction(
            self.account, 1000.0, "income", "Maaş", "x", detect_subscription=False)
        self.assertEqual(self._run(2026, 3, 15), 1)
        self.assertEqual(self._state(), (700.0, 500.0))

    def test_the_ledger_follows_the_move(self):
        from services.history_service import get_balance_at

        self._plan()
        self._run(2026, 3, 10)
        today = datetime.date.today().isoformat()
        balance = get_balance_at(today)
        self.assertEqual((balance["total_balance"], balance["savings_total"]), (9500.0, 500.0))

    # -- the plan itself ---------------------------------------------------------
    def test_changing_the_plan_does_not_move_twice_in_one_month(self):
        self._plan(amount=500.0)
        self._run(2026, 3, 10)
        self._plan(amount=800.0, day=1)
        self.assertEqual(self._run(2026, 3, 20), 0)
        self.assertEqual(self._run(2026, 4, 1), 1)
        self.assertEqual(self._state(), (8700.0, 1300.0))

    def test_a_cleared_plan_moves_nothing(self):
        from services.savings_auto_service import clear_contribution

        self._plan()
        self.assertTrue(clear_contribution(self.uid))
        self.assertFalse(clear_contribution(self.uid))
        self.assertEqual(self._run(2026, 3, 10), 0)

    def test_the_plan_of_a_deleted_goal_is_dropped(self):
        from services.savings_auto_service import get_contributions
        from services.savings_service import SavingsService

        self._plan()
        SavingsService.delete_goal(self.goal["id"], self.account, refund=False, goal_uid=self.uid)
        self.assertEqual(self._run(2026, 3, 10), 0)
        self.assertEqual(get_contributions(), {})

    def test_bad_plans_are_refused(self):
        from services.account_service import AccountService
        from services.savings_auto_service import get_contributions, set_contribution

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=5000.0)
        for uid, account, amount, day in (
            (self.uid, self.account, 0, 10), (self.uid, self.account, -5, 10),
            (self.uid, self.account, float("nan"), 10), (self.uid, self.account, 500, 0),
            (self.uid, self.account, 500, 32), (self.uid, card, 500, 10),
            (self.uid, 999, 500, 10), ("no-such-goal", self.account, 500, 10),
        ):
            with self.subTest(uid=uid, account=account, amount=amount, day=day):
                with self.assertRaises(ValueError):
                    set_contribution(uid, account, amount, day)
        self.assertEqual(get_contributions(), {})

    def test_it_runs_with_everything_else_that_is_due(self):
        from services.scheduled_service import process_due_items

        self._plan(day=1)
        self.assertTrue(process_due_items())
        self.assertEqual(self._state(), (9500.0, 500.0))
        self.assertFalse(process_due_items())


if __name__ == "__main__":
    unittest.main()
