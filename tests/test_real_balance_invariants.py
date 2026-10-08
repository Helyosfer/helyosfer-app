"""Pins that the drift accumulating in the `REAL` column does not break a BUSINESS DECISION.

WHY IT EXISTS: `adjust_account_balance` updates the balance with
`UPDATE accounts SET balance = balance + ?` -- the addition happens not in
Python but in SQLite's `REAL` column, so even if the Python side moves entirely
to `Decimal` the accumulation stays in binary floating point. Adding 0.01 a
hundred thousand times makes the raw value 999.9999999992356 (measurement:
`scripts/audit/measure_real_column_drift.py`).

THE TESTS HERE DO NOT SAY "the raw balance must equal the Decimal". Under the
current schema that would be a wrong expectation and would turn the gate
permanently red. What the application really guarantees is this: **the amount
shown to the user is correct and the decision taken is consistent with the
amount shown.** The mechanism keeping the drift away from the business decision
is clear too: the comparisons are made on the rounded value (`fiat()`, or
`ROUND(...)` on the SQL side).

These tests guard against that mechanism being removed. If anyone takes
`fiat()` out of a comparison or deletes a `ROUND(...)`, this goes red -- because
at that moment the user sees 100.00 lira on screen and becomes unable to spend
100.00 lira. That is a far more serious class than a display defect.

"""

import os
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from unittest import mock

_MUTATIONS = 10_000


class RealColumnDriftInvariants(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="helysofer-realinv-")
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

    def _drift(self, sql, ident, times=_MUTATIONS, step=0.01):
        """Produces the drift with the application's own SQL pattern."""
        from database.db import get_connection
        with closing(get_connection()) as conn, conn:
            for _ in range(times):
                conn.execute(sql, (step, ident))

    def _raw(self, table, column, ident):
        from database.db import get_connection
        with closing(get_connection()) as conn, conn:
            return conn.execute(
                f"SELECT {column} FROM {table} WHERE id=?", (ident,)
            ).fetchone()[0]

    def test_displayed_balance_is_the_exact_amount(self):
        """Even if the raw value drifts, the amount shown to the user must be correct."""
        from services.account_service import AccountService

        account_id = AccountService.create_account(
            "Drift", "checking", initial_balance=0.0)
        self._drift(
            "UPDATE accounts SET balance = balance + ? WHERE id=?", account_id)

        raw = self._raw("accounts", "balance", account_id)
        self.assertNotEqual(
            Decimal(repr(raw)), Decimal("100.00"),
            "Sapma üretilemedi; bu test artık ölçmek istediği şeyi ölçmüyor.",
        )
        self.assertEqual(AccountService.get_account(account_id)["balance"], 100.00)

    def test_spending_the_whole_displayed_balance_is_allowed(self):
        """If the screen says 100.00 lira, 100.00 lira must be spendable."""
        from services.account_service import AccountService

        account_id = AccountService.create_account(
            "Drift", "checking", initial_balance=0.0)
        self._drift(
            "UPDATE accounts SET balance = balance + ? WHERE id=?", account_id)

        allowed, reason = AccountService.check_spending_allowed(
            account_id, 100.00, "expense")
        self.assertTrue(allowed, f"gösterilen tutarın tamamı reddedildi: {reason}")

    def test_credit_card_limit_decision_matches_what_is_shown(self):
        """The whole remaining limit must be spendable, and one kurus more refused."""
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        card_id = AccountService.create_account(
            "Drift card", "credit_card", credit_limit=100.0)

        self._drift(
            "UPDATE accounts SET balance = balance - ? WHERE id=?",
            card_id, times=5_000)

        card = AccountService.get_account(card_id)
        self.assertEqual(card["debt"], 50.00)
        self.assertEqual(card["available_limit"], 50.00)

        allowed, reason = AccountService.check_spending_allowed(
            card_id, 50.00, "expense")
        self.assertTrue(allowed, f"kalan limitin tamamı reddedildi: {reason}")

        refused, _ = AccountService.check_spending_allowed(
            card_id, 50.01, "expense")
        self.assertFalse(refused, "limitin bir kuruş üstü kabul edildi")


        TransactionService.add_transaction(
            card_id, 50.00, "expense", "Audit", "sınır",
            detect_subscription=False)
        self.assertEqual(AccountService.get_account(card_id)["debt"], 100.00)

    def test_spending_the_whole_displayed_available_limit_is_allowed(self):
        """The case where the drift is UPWARD -- this is the genuinely dangerous one.

        In the previous test the debt stays a touch BELOW the exact value; in
        that direction the decisions come out right by coincidence even with
        `fiat()` removed (measured: with the guard removed that test stayed
        green). The danger is the other way: if the raw debt stays a touch
        ABOVE the exact value, the user sees "available limit 100.00" on screen
        and cannot spend 100.00.

        A 10,000 x 0.01 accumulation drifts in exactly that direction
        (100.00000000001425).

        THE GUARD IS TWO-LAYERED and was measured with mutation: when the debt
        is derived (`assert_spending_allowed`, `debt = fiat(...)`) and when the
        comparison is made (`fiat(debt + amount) > limit`). Removing ONLY ONE
        of the layers does not break this test -- the other swallows the drift.
        With both removed, exactly the feared failure appears:

            "Insufficient limit: available limit ₺100.00, spend ₺100.00."

        That is, the user sees the same two amounts and is refused. That is
        what the test measures; a single-point mutation not breaking it is not
        the gate's weakness but the guard's redundancy.
        """
        from services.account_service import AccountService

        card_id = AccountService.create_account(
            "Drift card", "credit_card", credit_limit=200.0)
        self._drift(
            "UPDATE accounts SET balance = balance - ? WHERE id=?",
            card_id, times=10_000)

        card = AccountService.get_account(card_id)
        self.assertEqual(card["debt"], 100.00)
        self.assertEqual(card["available_limit"], 100.00)

        allowed, reason = AccountService.check_spending_allowed(
            card_id, 100.00, "expense")
        self.assertTrue(
            allowed,
            f"ekranda gösterilen kullanılabilir limitin tamamı reddedildi: {reason}",
        )

    def test_withdrawing_the_whole_displayed_savings_is_allowed(self):
        """If the goal shows 300.00 lira, 300.00 lira must be withdrawable.

        This is a bug that really happened once: the
        `ROUND(current_amount, 2) >= ROUND(?, 2)` guard inside
        `savings_service` exists for exactly this and its comment tells the
        story. The test prevents that guard being removed.
        """
        from services.account_service import AccountService
        from services.savings_service import SavingsService

        account_id = AccountService.create_account(
            "A", "checking", initial_balance=1000.0)
        goal_id = SavingsService.create_goal("Drift goal", 1000.0)
        self._drift(
            "UPDATE savings_goals SET current_amount = current_amount + ? "
            "WHERE id=?", goal_id, times=30_000)

        raw = self._raw("savings_goals", "current_amount", goal_id)
        self.assertNotEqual(
            Decimal(repr(raw)), Decimal("300.00"),
            "Sapma üretilemedi; bu test artık ölçmek istediği şeyi ölçmüyor.",
        )
        SavingsService.withdraw_from_goal(goal_id, 300.00, account_id)


if __name__ == "__main__":
    unittest.main()
