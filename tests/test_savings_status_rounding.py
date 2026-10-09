"""A savings goal's status cannot be decided at two different precisions in the same service.

WHY IT EXISTS: `savings_service` asks the same economic question in three
places, but at kurus precision in two and with the raw `REAL` value in one:

    completion       ROUND(current_amount, 2) >= ROUND(target_amount, 2)
    withdrawal enough ROUND(current_amount, 2) >= ROUND(?, 2)
    status revert     current_amount < target_amount        <-- unrounded

`current_amount` accumulates via `current_amount + ?`, so it carries binary
floating-point residue (the comment in the same file already records the
"3000 x 0.10 -> 299.9999999999997" example). The result: a goal holding
exactly the target shows "10.40 / 10.40" on screen but its label reads
"active".

It is produced through ordinary use -- eleven service calls, realistic
amounts. The money is not wrong; what is wrong is the goal not being counted
as completed.

"""

import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


class SavingsStatusUsesKurusPrecision(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="helyosfer-savstatus-")
        root = Path(self.tempdir.name)
        self.db_patch = mock.patch("database.db.DB_NAME", str(root / "finance.db"))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=os.urandom(32)
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database
        initialize_database()

        from services.account_service import AccountService
        self.account_id = AccountService.create_account(
            "Kaynak", "checking", initial_balance=1000.0)

    def _goal_row(self, goal_id):
        from database.db import get_connection
        with closing(get_connection()) as conn, conn:
            return conn.execute(
                "SELECT current_amount, target_amount, status "
                "FROM savings_goals WHERE id=?", (goal_id,)
            ).fetchone()

    def _drifted_completed_goal(self):
        """A goal that holds the target EXACTLY but whose raw value sits a touch below.

        The sequence is deliberately made of service calls only -- injecting
        the drift directly with SQL would be exercising a state that cannot
        arise in production. What produces the drift is an over-deposit
        followed by withdrawing the excess: 5.40 + 10.00 - 5.00 is exactly
        10.40, and it sits at 10.399999999999999 in binary floating point.
        """
        from services.savings_service import SavingsService

        goal_id = SavingsService.create_goal("Bozuk para", 10.40)
        for _ in range(9):
            SavingsService.deposit_to_goal(goal_id, 0.60, self.account_id)
        SavingsService.deposit_to_goal(goal_id, 10.00, self.account_id)
        SavingsService.withdraw_from_goal(goal_id, 5.00, self.account_id)
        return goal_id

    def test_completed_goal_survives_withdrawing_the_excess(self):
        """THE REAL BUG: a goal still holding the target must not fall to "active"."""
        from utils.financial_decimal import fiat

        goal_id = self._drifted_completed_goal()
        current, target, status = self._goal_row(goal_id)


        self.assertLess(
            current, target,
            "ham değer sapmadı; dizi artık hatayı üretmiyor olabilir",
        )
        self.assertEqual(
            fiat(current), fiat(target),
            "kuruş hassasiyetinde hedef tutulmuyor; senaryo yanlış kurulmuş",
        )
        self.assertEqual(
            status, "tamamlandi",
            f"ekranda {fiat(current)}/{fiat(target)} yazarken hedef "
            f"'{status}' olarak işaretlendi",
        )

    def test_status_returns_to_active_when_the_goal_really_drops_below(self):
        """The complementary case: the fix must not make "completed" sticky.

        A withdrawal that really does drop below the target at kurus precision
        must return the status to "active". Without this test, rounding the
        comparison could have turned into the bug "once a goal is completed it
        stays completed forever".
        """
        from services.savings_service import SavingsService

        goal_id = self._drifted_completed_goal()
        SavingsService.withdraw_from_goal(goal_id, 0.01, self.account_id)

        current, target, status = self._goal_row(goal_id)
        self.assertLess(round(current, 2), round(target, 2))
        self.assertEqual(
            status, "aktif",
            "hedefin altına düşüldüğü hâlde 'tamamlandı' kaldı",
        )


if __name__ == "__main__":
    unittest.main()
