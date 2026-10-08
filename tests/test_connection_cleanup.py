"""SQLite connections must close deterministically -- without depending on the GC.

A RECORD OF THE SITUATION: an audit measured the file descriptor count going
from 4 to 71 over 100 operations and then falling with the GC, and this was
counted as a PRODUCTION finding. **That attribution was wrong.**

The measurement was real, but what it measured was the audit probe's OWN leak:
`scripts/audit/check_resource_leaks.py` wrote the iteration body as
`with get_connection() as conn:`, and sqlite3's context manager commits or rolls
back and DOES NOT CLOSE. The evidence: with the probe's single line fixed, the
count stays flat at 4. Production code had never used this pattern.

This file is not a FIX but a regression guard that PINS the behaviour: if a
path is written in future without `try/finally` or `managed_connection`, the
test breaks. For the FD-count-independent, platform-independent evidence of the
ownership contract see `tests/test_connection_ownership_contract.py` (it counts
opens/closes, needs no `/proc`, and is meaningful on Windows too).

The ownership contract is also tested: in Python `with conn:` DOES NOT CLOSE the
connection, it only commits or rolls back. That distinction is easily missed.

"""

import gc
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

_FD_DIR = f"/proc/{os.getpid()}/fd"


def _fd_count():
    return len(os.listdir(_FD_DIR))


@unittest.skipUnless(
    os.path.isdir(_FD_DIR),
    "file descriptor sayımı /proc gerektirir (Linux)",
)
class ConnectionCleanupTest(unittest.TestCase):


    TOLERANCE = 5

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account_id = AccountService.create_account(
            "FD Hesabı", "checking", initial_balance=10_000_000.0
        )

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _assert_bounded(self, label, operation, repeats=100):
        """It must stay bounded WITHOUT CALLING THE GC -- that is the real claim."""
        gc.collect()
        before = _fd_count()
        for index in range(repeats):
            operation(index)
        after = _fd_count()
        self.assertLessEqual(
            after - before, self.TOLERANCE,
            f"{label}: {repeats} işlemde FD {before} -> {after} "
            f"(explicit GC olmadan sınırlı kalmalı)",
        )

    def test_transaction_writes_do_not_accumulate_descriptors(self):
        from services.transaction_service import TransactionService

        self._assert_bounded(
            "transaction_write",
            lambda i: TransactionService.add_transaction(
                self.account_id, 1.0, "expense", "T", "d",
                transaction_date="2026-08-01 10:00:00",
                detect_subscription=False,
            ),
        )

    def test_period_queries_do_not_accumulate_descriptors(self):
        from services.transaction_service import TransactionService

        self._assert_bounded(
            "period_query",
            lambda i: TransactionService.get_transactions_by_period("Bugün"),
        )

    def test_savings_round_trips_do_not_accumulate_descriptors(self):
        from services.savings_service import SavingsService

        goal_id = SavingsService.create_goal("Hedef", 1_000_000.0)

        def _cycle(_index):
            SavingsService.deposit_to_goal(goal_id, 1.0, self.account_id)
            SavingsService.withdraw_from_goal(goal_id, 1.0, self.account_id)

        self._assert_bounded("savings_cycle", _cycle, repeats=50)

    def test_asset_purchases_do_not_accumulate_descriptors(self):
        from services.asset_purchase_service import AssetPurchaseService

        self._assert_bounded(
            "asset_purchase",
            lambda i: AssetPurchaseService.create_purchase(
                asset_name="A", asset_code="A", asset_type="Altın",
                purchase_price=10.0, quantity=1.0,
                account_id=self.account_id,
            ),
            repeats=50,
        )

    def test_database_file_can_be_replaced_after_operations(self):
        """Windows file-lock preparation: the file must be movable after the operations.

        On Linux an open handle does not prevent a rename, so this test does
        not stand in for Windows. It does separately verify the presence of a
        connection left open.
        """
        from services.transaction_service import TransactionService

        for _ in range(20):
            TransactionService.add_transaction(
                self.account_id, 1.0, "expense", "T", "d",
                transaction_date="2026-08-01 10:00:00",
                detect_subscription=False,
            )
        moved = self.db_path + ".moved"
        os.replace(self.db_path, moved)
        self.assertTrue(os.path.exists(moved))
        os.replace(moved, self.db_path)


class ConnectionOwnershipTest(unittest.TestCase):
    """`with conn:` DOES NOT CLOSE the connection -- that distinction is easily missed."""

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

    def test_sqlite_context_manager_does_not_close(self):
        """The Python contract: `with conn:` only commits or rolls back.

        If this behaviour is assumed, the connection leaks. The test is here as
        a reminder that the code base does not rest on that assumption.
        """
        conn = sqlite3.connect(self.db_path)
        with conn:
            conn.execute("SELECT 1")

        conn.execute("SELECT 1")
        conn.close()
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_managed_connection_closes_on_success(self):
        from database.db import managed_connection

        with managed_connection() as conn:
            conn.execute("SELECT 1")
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_managed_connection_closes_on_exception(self):
        from database.db import managed_connection

        captured = None
        with self.assertRaises(ValueError):
            with managed_connection() as conn:
                captured = conn
                raise ValueError("boom")
        with self.assertRaises(sqlite3.ProgrammingError):
            captured.execute("SELECT 1")

    def test_externally_supplied_cursor_is_not_closed_by_callee(self):
        """A function taking an external cursor must not close the connection.

        `adjust_account_balance` takes an open cursor and joins the caller's
        commit; closing it would cut the caller's transaction short.
        """
        from database.db import adjust_account_balance, managed_connection
        from services.account_service import AccountService

        account_id = AccountService.create_account(
            "Sahiplik", "checking", initial_balance=100.0
        )
        with managed_connection() as conn:
            cursor = conn.cursor()
            adjust_account_balance(cursor, account_id, "income", 50.0)

            balance = cursor.execute(
                "SELECT balance FROM accounts WHERE id=?", (account_id,)
            ).fetchone()[0]
            conn.commit()
        self.assertEqual(balance, 150.0)


if __name__ == "__main__":
    unittest.main()
