"""DECISIONS about money must be made at kurus precision.

`accounts.balance` and `savings_goals.current_amount` are SQLite REAL columns
accumulating via `column + ?`, so they can carry binary floating-point residue.
Measured: in realistic use that residue IS NOT VISIBLE ON SCREEN (12 x 500.00
or 1000 x 1.00 come out exact), so moving the columns to TEXT -- and taking the
migration risk -- is not justified by measurement.

Where the invisible residue does harm is not the STORAGE but the DECISION taken
on it: a threshold comparison makes the residue visible. These tests pin those
decisions.

"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock


class MoneyDecisionPrecisionTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database

        initialize_database()

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _drift_goal_to(self, goal_id, deposits, amount):
        """Accumulates the goal directly with SQL and produces the real float residue."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            for _ in range(deposits):
                conn.execute(
                    "UPDATE savings_goals SET current_amount = "
                    "current_amount + ? WHERE id = ?",
                    (amount, goal_id),
                )
            conn.commit()
            return conn.execute(
                "SELECT current_amount FROM savings_goals WHERE id = ?",
                (goal_id,),
            ).fetchone()[0]

    def test_user_can_withdraw_the_balance_the_screen_shows_them(self):
        """It must be possible to withdraw the 300.00 lira the screen shows.

        This is the sharpest case found: for someone who deposited 3000 x 0.10
        lira, the savings sit at 299.9999999999997 in the REAL column and show
        as "300.00 lira" on screen -- but because `current_amount >= ?` does not
        hold, the withdrawal WOULD BE REFUSED with "the goal does not hold that
        much". The application was not handing over the money it was itself
        showing.
        """
        from services.savings_service import SavingsService

        goal_id = SavingsService.create_goal("Tatil", 1000.0)
        stored = self._drift_goal_to(goal_id, 3000, 0.10)


        self.assertNotEqual(
            stored, 300.0, "Test kurulumu artığı üretemedi; vaka geçersiz"
        )
        self.assertEqual(f"{stored:.2f}", "300.00", "Ekranda 300,00 görünmeli")

        account_id = self._make_account(balance=0.0)
        SavingsService.withdraw_from_goal(goal_id, 300.0, account_id)

        with closing(sqlite3.connect(self.db_path)) as conn:
            balance = conn.execute(
                "SELECT balance FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()[0]
        self.assertEqual(round(balance, 2), 300.0)

    def test_goal_completes_when_the_target_is_actually_reached(self):
        """A goal must be 'completed' when the target is actually reached at kurus precision.

        The target 300.01 was chosen so that AFTER the last deposit the raw
        total stays just BELOW the threshold: 299.9999999999997 + 0.01 =
        300.00999999999..., so `current_amount >= target_amount` does not hold,
        but rounded to the kurus 300.01 >= 300.01 does.

        My first version used a target of 300.00 and PASSED ON THE OLD CODE TOO
        -- the deposit already exceeded the threshold, so the test discriminated
        nothing.
        """
        from services.savings_service import SavingsService

        goal_id = SavingsService.create_goal("Bisiklet", 300.01)
        stored = self._drift_goal_to(goal_id, 3000, 0.10)
        self.assertNotEqual(stored, 300.0, "Test kurulumu artığı üretemedi")

        account_id = self._make_account(balance=10.0)
        SavingsService.deposit_to_goal(goal_id, 0.01, account_id)

        with closing(sqlite3.connect(self.db_path)) as conn:
            current, status = conn.execute(
                "SELECT current_amount, status FROM savings_goals "
                "WHERE id = ?", (goal_id,)
            ).fetchone()


        self.assertLess(
            current, 300.01,
            "Ham toplam eşiği aşıyorsa test eski kodda da geçer; vaka geçersiz",
        )
        self.assertEqual(f"{current:.2f}", "300.01")
        self.assertEqual(status, "tamamlandi")

    def test_spending_a_kurus_under_the_limit_is_allowed(self):
        """A spend a millionth below the limit must not be refused.

        Had it been refused, the error message would have shown THE SAME two
        amounts -- "available limit ₺1,000.00, spend ₺1,000.00" -- that is, a
        refusal the user could not resolve.
        """
        from services.account_service import AccountService

        card_id = AccountService.create_account(
            "Limit kart", "credit_card", credit_limit=1000.0
        )
        allowed, reason = AccountService.check_spending_allowed(
            card_id, 1000.0 + 1e-9, "expense"
        )
        self.assertTrue(allowed, reason)

    def _make_account(self, balance):
        from services.account_service import AccountService

        return AccountService.create_account(
            f"Hesap {balance}", "checking", initial_balance=balance
        )


if __name__ == "__main__":
    unittest.main()
