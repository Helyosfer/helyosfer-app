import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.db import get_connection, DEFAULT_ACCOUNT_ID
from services.savings_service import SavingsService, STATUS_ACTIVE, STATUS_COMPLETED


def _get_balance():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM accounts WHERE id = ?", (DEFAULT_ACCOUNT_ID,))
        return cur.fetchone()["balance"]
    finally:
        conn.close()


def _set_balance(amount):
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE accounts SET balance = ? WHERE id = ?",
            (float(amount), DEFAULT_ACCOUNT_ID),
        )
        conn.commit()
    finally:
        conn.close()


class SavingsServiceTest(unittest.TestCase):
    """Runs on an isolated temporary database -- it DOES NOT TOUCH the real finance.db.

    FIX: this used to run against the real finance.db and assumed
    DEFAULT_ACCOUNT_ID (=1) already had a balance. That always worked on the
    developer's local machine (there was months of accumulated real account
    data) but carried two real problems: (1) on a fresh installation/CI
    checkout the `accounts` table is EMPTY -- the default account seed was
    deliberately removed (the "a fresh installation produces no balance that
    does not belong to the user" contract, see OrphanTransactionGuardTest) --
    so `_get_balance()` returned `None` and `None["balance"]` raised
    `TypeError`; (2) every run
    set the REAL user's balance to 10,000 and then restored it -- if an error
    happened before ever reaching tearDown, the real balance would be left
    stuck at the test value.

    SavingsService.deposit_to_goal/withdraw_from_goal/delete_goal all use the
    `account_id=DEFAULT_ACCOUNT_ID` default; because the tests call it
    unchanged, the FIRST account created in the isolated DB (id 1, via
    autoincrement) matches DEFAULT_ACCOUNT_ID -- so no call site had to be
    changed to pass account_id.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patcher = mock.patch("database.db.DB_NAME", self.db_path)
        self._patcher.start()

        from database.init_db import initialize_database
        initialize_database()

        from services.account_service import AccountService
        AccountService.create_account(
            "Test Hesabı", "checking", initial_balance=0.0
        )

        _set_balance(10000.0)
        self.balance_before = _get_balance()
        self.goal_id = SavingsService.create_goal(
            "Test Yaz Tatili (Bali)", 50000.0, "2026-08-01"
        )

    def tearDown(self):
        try:
            SavingsService.delete_goal(self.goal_id)
            self.assertAlmostEqual(
                _get_balance(), self.balance_before, places=2,
                msg="Hedef temizliği sonrası test bakiyesi başlangıca dönmedi",
            )
        finally:
            self._patcher.stop()
            os.unlink(self.db_path)

    def test_deposit_isolates_from_main_balance(self):
        """Transferring 1,000 lira must lower the main balance and raise the goal by the same amount."""
        goal = SavingsService.deposit_to_goal(self.goal_id, 1000.0)
        self.assertAlmostEqual(_get_balance(), self.balance_before - 1000.0, places=2)
        self.assertAlmostEqual(goal["current_amount"], 1000.0, places=2)
        self.assertEqual(goal["status"], STATUS_ACTIVE)
        self.assertEqual(goal["goal_name"], "Test Yaz Tatili (Bali)")

    def test_withdraw_returns_to_main_balance(self):
        SavingsService.deposit_to_goal(self.goal_id, 1000.0)
        goal = SavingsService.withdraw_from_goal(self.goal_id, 400.0)
        self.assertAlmostEqual(_get_balance(), self.balance_before - 600.0, places=2)
        self.assertAlmostEqual(goal["current_amount"], 600.0, places=2)

    def test_deposit_beyond_balance_drives_account_negative(self):
        """The insufficient-balance guard was removed: the transfer always
        happens and the main account can go negative. The balance and the goal
        must stay consistent together (no half operation -- both must move by
        the same amount).
        """
        huge = _get_balance() + 1_000_000.0
        goal = SavingsService.deposit_to_goal(self.goal_id, huge)
        self.assertAlmostEqual(
            _get_balance(), self.balance_before - huge, places=2,
        )
        self.assertAlmostEqual(goal["current_amount"], huge, places=2)
        self.assertLess(_get_balance(), 0.0)

    def test_overdraw_from_goal_rejected(self):
        SavingsService.deposit_to_goal(self.goal_id, 100.0)
        with self.assertRaises(ValueError):
            SavingsService.withdraw_from_goal(self.goal_id, 500.0)
        self.assertAlmostEqual(_get_balance(), self.balance_before - 100.0, places=2)

    def test_goal_completion_status(self):
        """The status must become 'tamamlandi' on reaching the goal; a deposit onto a completed one must be refused."""

        small_goal = SavingsService.create_goal("Test Mini Hedef", 200.0)
        try:
            goal = SavingsService.deposit_to_goal(small_goal, 200.0)
            self.assertEqual(goal["status"], STATUS_COMPLETED)
            with self.assertRaises(ValueError):
                SavingsService.deposit_to_goal(small_goal, 50.0)

            goal = SavingsService.withdraw_from_goal(small_goal, 50.0)
            self.assertEqual(goal["status"], STATUS_ACTIVE)
        finally:
            SavingsService.delete_goal(small_goal)

    def test_goal_name_encrypted_at_rest(self):
        """goal_name must not sit as plain text in the database."""
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT goal_name FROM savings_goals WHERE id = ?", (self.goal_id,))
            raw = cur.fetchone()["goal_name"]
        finally:
            conn.close()
        self.assertNotIn("Bali", str(raw))


if __name__ == "__main__":
    unittest.main()
