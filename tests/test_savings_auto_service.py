"""A monthly contribution to a savings goal moves once for every month, on its day."""

import datetime
import os
import tempfile
import unittest
from unittest import mock

from tests.clock import Clock


class SavingsAutoServiceTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.clock = Clock(datetime.datetime(2026, 3, 1, 9, 0))
        self.clock.__enter__()
        from database.init_db import initialize_database
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 10000.0)
        goal_id = SavingsService.create_goal("Holiday", 3000.0)
        self.goal = next(g for g in SavingsService.get_goals() if g["id"] == goal_id)
        self.uid = self.goal["goal_uid"]

    def tearDown(self):
        self.clock.__exit__(None, None, None)
        self._patch.stop()
        os.unlink(self.db_path)

    def _state(self):
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        goal = next(g for g in SavingsService.get_goals() if g["goal_uid"] == self.uid)
        return AccountService.get_account(self.account)["balance"], goal["current_amount"]

    def _on(self, year, month, day):
        self.clock.move_to(datetime.datetime(year, month, day, 9, 0))

    def _run(self, year, month, day):
        """Opens the application on that day."""
        from services.savings_auto_service import process_due_contributions

        self._on(year, month, day)
        return process_due_contributions()

    def _plan(self, amount=500.0, day=10, account=None):
        from services.savings_auto_service import set_contribution

        set_contribution(self.uid, account or self.account, amount, day)

    def _moves(self):
        """The days the goal received money on, with the amounts."""
        from database.db import get_connection

        conn = get_connection()
        try:
            return [
                (row[0][:10], row[1]) for row in conn.execute(
                    "SELECT ts, delta FROM balance_events"
                    " WHERE entity_type = 'savings_goal' AND delta != 0 ORDER BY ts")
            ]
        finally:
            conn.close()

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
        # Moved two days late, it is still recorded on its day.
        self.assertEqual(self._moves(), [("2026-03-10", 500.0), ("2026-04-10", 500.0)])

    def test_missed_months_are_made_up_for_each_on_its_day(self):
        self._plan()
        self._run(2026, 3, 10)
        self.assertEqual(self._run(2026, 7, 20), 4)
        self.assertEqual(self._state(), (7500.0, 2500.0))
        self.assertEqual(
            [day for day, _amount in self._moves()],
            ["2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10"],
        )

    def test_a_day_late_in_the_month_is_not_lost_when_opened_after_it(self):
        self._plan(day=31)
        self.assertEqual(self._run(2026, 3, 30), 0)
        # Not opened on the 31st, nor on the last day of April.
        self.assertEqual(self._run(2026, 4, 2), 1)
        self.assertEqual(self._run(2026, 5, 5), 1)
        self.assertEqual(
            self._moves(), [("2026-03-31", 500.0), ("2026-04-30", 500.0)])

    def test_day_31_falls_on_the_last_day_of_a_shorter_month(self):
        self._on(2026, 2, 1)
        self._plan(day=31)
        self.assertEqual(self._run(2026, 2, 27), 0)
        self.assertEqual(self._run(2026, 2, 28), 1)

    def test_the_first_is_the_next_time_its_day_comes_round(self):
        # Set on the 12th for the 10th: this month's day has gone by.
        self._on(2026, 3, 12)
        self._plan(day=10)
        self.assertEqual(self._run(2026, 3, 28), 0)
        self.assertEqual(self._run(2026, 4, 10), 1)
        self.assertEqual(self._moves(), [("2026-04-10", 500.0)])

    def test_set_on_its_day_it_moves_that_day(self):
        self._on(2026, 3, 10)
        self._plan(day=10)
        self.assertEqual(self._run(2026, 3, 10), 1)

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

    def test_making_up_stops_when_the_goal_is_full(self):
        self._plan(amount=1200.0)
        # Six months away: the goal needs only three contributions.
        self.assertEqual(self._run(2026, 8, 20), 3)
        self.assertEqual(self._state(), (7000.0, 3000.0))
        self.assertEqual(
            self._moves(), [("2026-03-10", 1200.0), ("2026-04-10", 1200.0), ("2026-05-10", 600.0)])

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

    def test_making_up_takes_only_the_months_the_account_can_cover(self):
        from services.transaction_service import TransactionService

        self._plan(amount=500.0)
        TransactionService.add_transaction(
            self.account, 8900.0, "expense", "Taksi", "x", detect_subscription=False)
        # 1.100 is left: two months of the four owed, and the rest wait.
        self.assertEqual(self._run(2026, 6, 20), 2)
        self.assertEqual(self._state(), (100.0, 1000.0))
        TransactionService.add_transaction(
            self.account, 5000.0, "income", "Maaş", "x", detect_subscription=False)
        self.assertEqual(self._run(2026, 6, 21), 2)
        self.assertEqual(
            [day for day, _amount in self._moves()],
            ["2026-03-10", "2026-04-10", "2026-05-10", "2026-06-10"],
        )

    def test_the_ledger_follows_the_move(self):
        from services.history_service import get_balance_at

        self._plan()
        self._run(2026, 3, 10)
        balance = get_balance_at("2026-03-10")
        self.assertEqual((balance["total_balance"], balance["savings_total"]), (9500.0, 500.0))
        # Made up for later, each month is in the history on its own day.
        self._run(2026, 6, 20)
        for day, expected in (("2026-04-09", (9500.0, 500.0)), ("2026-04-10", (9000.0, 1000.0)),
                              ("2026-05-31", (8500.0, 1500.0)), ("2026-06-20", (8000.0, 2000.0))):
            with self.subTest(day=day):
                balance = get_balance_at(day)
                self.assertEqual((balance["total_balance"], balance["savings_total"]), expected)

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

    def test_a_plan_set_again_after_a_break_does_not_take_the_break(self):
        from services.savings_auto_service import clear_contribution

        self._plan()
        self._run(2026, 3, 10)
        clear_contribution(self.uid)
        self._on(2026, 7, 20)
        self._plan()
        self.assertEqual(self._run(2026, 7, 21), 0)
        self.assertEqual(self._run(2026, 8, 10), 1)
        self.assertEqual(self._state(), (9000.0, 1000.0))

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
