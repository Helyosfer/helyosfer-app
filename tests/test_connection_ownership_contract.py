"""The connection ownership contract -- evidence INDEPENDENT of FD counting.

WHY A SEPARATE FILE: `tests/test_connection_cleanup.py` COUNTS file
descriptors. That measurement is fragile for two reasons: (1) it works only on
Linux, via `/proc`, and (2) because leaked `sqlite3.Connection` objects enter a
reference cycle through the statement cache, the descriptors stay up until the
generational GC -- so an FD delta can indicate "the GC has not run yet" rather
than "there is no leak". That exact ambiguity led to a past audit finding being
misinterpreted: what was taken for a leak was the measurement probe itself.

The tests here COUNT OPENS AND CLOSES instead: `sqlite3.connect` is wrapped,
every opened connection is recorded, and `opened == closed` is asserted at the
end of the block. That measurement is independent of the platform and of GC
timing, so it means the same thing on Windows.

"""

import ast
import gc
import os
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]


class _ConnectionLedger:
    """Records every sqlite3 connection opened and closed within the process."""

    def __init__(self):
        self.opened = []
        self.closed = []

    @property
    def leaked(self):
        closed = {id(conn) for conn in self.closed}
        return [conn for conn in self.opened if id(conn) not in closed]


@contextmanager
def connection_ledger():
    ledger = _ConnectionLedger()
    real_connect = sqlite3.connect
    real_close = sqlite3.Connection.close

    class _Tracked(sqlite3.Connection):
        def close(self):
            ledger.closed.append(self)
            return real_close(self)

    def _connect(*args, **kwargs):
        kwargs.setdefault("factory", _Tracked)
        conn = real_connect(*args, **kwargs)
        ledger.opened.append(conn)
        return conn

    with mock.patch("sqlite3.connect", _connect):
        yield ledger


class _InjectedFailure(Exception):
    """An error raised deliberately in the middle of setup."""


class _FailingCursor:
    """N'inci `execute`'ta patlayan cursor vekili."""

    def __init__(self, inner, budget):
        self._inner = inner
        self._budget = budget

    def execute(self, *args, **kwargs):
        if self._budget[0] <= 0:
            raise _InjectedFailure("kurulum ortasında kesinti")
        self._budget[0] -= 1
        return self._inner.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _FailingConnection:
    """Wraps the real connection; `close()` REACHES the real object.

    If the proxy swallowed the close itself the test would fool itself -- the
    ledger has to see the real `sqlite3.Connection.close()` call.
    """

    def __init__(self, inner, fail_after):
        self._inner = inner
        self._budget = [fail_after]

    def cursor(self, *args, **kwargs):
        return _FailingCursor(self._inner.cursor(*args, **kwargs), self._budget)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@contextmanager
def _failing_connection(module_path, *, fail_after):
    from database.db import get_connection as real_get_connection

    def _factory(*args, **kwargs):
        return _FailingConnection(real_get_connection(*args, **kwargs), fail_after)

    with mock.patch(f"{module_path}.get_connection", _factory):
        yield


class _TempProfile(unittest.TestCase):
    """Every test runs with its own temporary database; the real profile is untouched."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(lambda: os.path.exists(self.db_path) and os.unlink(self.db_path))
        from database.init_db import initialize_database

        initialize_database()

    def _account(self, balance=1_000_000.0):
        from services.account_service import AccountService

        return AccountService.create_account("Sözleşme", "checking", balance)


class OwnershipContractTest(_TempProfile):
    def test_internally_owned_connection_closes_on_success(self):
        """(1) A path that opens its own connection closes it on the success path."""
        from services.account_service import AccountService

        with connection_ledger() as ledger:
            AccountService.create_account("Başarı", "checking", 10.0)
        self.assertEqual(len(ledger.opened), len(ledger.closed))
        self.assertEqual(ledger.leaked, [])

    def test_internally_owned_connection_closes_on_exception(self):
        """(2) It closes on the exception path too -- that was where the real leak risk was."""
        from services.transaction_service import TransactionService

        with connection_ledger() as ledger:
            with self.assertRaises(ValueError):

                TransactionService.add_transaction(
                    999_999, 1.0, "expense", "T", "d",
                    transaction_date="2026-08-01 10:00:00",
                    detect_subscription=False,
                )
        self.assertEqual(ledger.leaked, [],
                         "istisna yolunda bağlantı açık kaldı")

    def test_externally_supplied_connection_is_not_closed_by_callee(self):
        """(3) The callee DOES NOT CLOSE an externally supplied connection."""
        from database.db import adjust_account_balance, managed_connection

        account_id = self._account(100.0)
        with managed_connection() as conn:
            cursor = conn.cursor()
            adjust_account_balance(cursor, account_id, "income", 50.0)

            balance = cursor.execute(
                "SELECT balance FROM accounts WHERE id=?", (account_id,)
            ).fetchone()[0]
            conn.commit()
        self.assertEqual(balance, 150.0)

    def test_nested_operation_does_not_close_outer_connection(self):
        """(4) A nested call does not close the outer connection."""
        from database.db import managed_connection, record_balance_event, ACCOUNT

        account_id = self._account(100.0)
        with managed_connection() as conn:
            cursor = conn.cursor()
            record_balance_event(cursor, ACCOUNT, account_id, 5.0, 105.0, "test")
            record_balance_event(cursor, ACCOUNT, account_id, 5.0, 110.0, "test")
            conn.commit()
            self.assertEqual(
                cursor.execute("SELECT 1").fetchone()[0], 1,
                "dış bağlantı iç çağrılardan sonra kullanılabilir olmalı",
            )

    def test_hundred_reads_open_and_close_symmetrically(self):
        """(5) 100 okuma — explicit GC OLMADAN opened == closed."""
        from services.transaction_service import TransactionService

        self._account()
        with connection_ledger() as ledger:
            for _ in range(100):
                TransactionService.get_transactions_by_period("Bugün")
        self.assertEqual(ledger.leaked, [])
        self.assertGreaterEqual(len(ledger.opened), 100,
                                "iş yükü gerçekten bağlantı açmalı")

    def test_hundred_writes_open_and_close_symmetrically(self):
        """(6) 100 yazma — explicit GC OLMADAN opened == closed."""
        from services.transaction_service import TransactionService

        account_id = self._account()
        with connection_ledger() as ledger:
            for _ in range(100):
                TransactionService.add_transaction(
                    account_id, 1.0, "expense", "T", "d",
                    transaction_date="2026-08-01 10:00:00",
                    detect_subscription=False,
                )
        self.assertEqual(ledger.leaked, [])

    def test_initialize_database_leaves_no_open_connection(self):
        """(7) No connection is left open after a migration/schema setup."""
        from database.init_db import initialize_database

        with connection_ledger() as ledger:
            initialize_database()
        self.assertEqual(ledger.leaked, [])

    def test_initialize_database_closes_when_a_migration_step_fails(self):
        """(7b) The connection closes even if it blows up MID-setup.

        This is the reason the try/finally wrapper in `database/init_db.py`
        exists. On Windows a leaked handle means a lock on finance.db; the next
        restore/rename step would be blocked.
        """
        from database.init_db import initialize_database

        with connection_ledger() as ledger:
            with _failing_connection("database.init_db", fail_after=5):
                with self.assertRaises(_InjectedFailure):
                    initialize_database()
        self.assertEqual(ledger.leaked, [],
                         "kurulum hata verdiğinde bağlantı açık kaldı")

    def test_database_file_is_replaceable_after_backup_round_trip(self):
        """(8) The database file is movable after a backup/restore round trip."""
        from services.backup_service import create_backup, verify_backup

        self._account()
        with tempfile.TemporaryDirectory() as root:
            key_path = Path(root) / "encryption.key"
            key_path.write_bytes(os.urandom(32))
            os.chmod(key_path, 0o600)
            package = Path(root) / "p.helysofer-backup"
            create_backup(package, "yalnizca-test-icin-parola",
                          db_path=self.db_path, key_path=str(key_path))
            verify_backup(package, "yalnizca-test-icin-parola")
        moved = self.db_path + ".moved"
        os.replace(self.db_path, moved)
        os.replace(moved, self.db_path)

    def test_background_thread_closes_its_own_connection(self):
        """(9) A background thread closes its own connection."""
        import threading

        from services.transaction_service import TransactionService

        account_id = self._account()
        errors = []

        def worker():
            try:
                for _ in range(20):
                    TransactionService.add_transaction(
                        account_id, 1.0, "expense", "BG", "d",
                        transaction_date="2026-08-01 10:00:00",
                        detect_subscription=False,
                    )
            except Exception as exc:  # pragma: no cover - diagnostic path
                errors.append(exc)

        with connection_ledger() as ledger:
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join(timeout=60)
        self.assertFalse(thread.is_alive(), "worker zamanında bitmedi")
        self.assertEqual(errors, [])
        self.assertEqual(ledger.leaked, [],
                         "arka plan thread'i bağlantı bıraktı")

    def test_early_return_path_closes_connection(self):
        """(10) The early-return path leaves no connection behind.

        `ledger_start_date` returns EARLY (None) when the ledger is empty -- the
        only path written with an ownership-sensitive `own` flag, which is why
        it is here.
        """
        from services.history_service import ledger_start_date

        with connection_ledger() as ledger:
            ledger_start_date()
        self.assertEqual(ledger.leaked, [])

    def test_interrupted_cursor_iteration_preserves_ownership(self):
        """(11) The contract is not broken when a cursor iteration is cut short."""
        from database.db import managed_connection

        account_id = self._account()
        from services.transaction_service import TransactionService

        for _ in range(10):
            TransactionService.add_transaction(
                account_id, 1.0, "expense", "T", "d",
                transaction_date="2026-08-01 10:00:00",
                detect_subscription=False,
            )
        with connection_ledger() as ledger:
            with self.assertRaises(RuntimeError):
                with managed_connection() as conn:
                    for index, _row in enumerate(
                            conn.execute("SELECT id FROM transactions")):
                        if index == 3:
                            raise RuntimeError("iterasyon yarıda kesildi")
        self.assertEqual(ledger.leaked, [],
                         "yarıda kesilen cursor bağlantıyı açık bıraktı")

    def test_no_connection_survives_a_full_session(self):
        """(12) No connection is left open at the end of a mixed session."""
        from services.account_service import AccountService
        from services.savings_service import SavingsService
        from services.transaction_service import TransactionService

        with connection_ledger() as ledger:
            account_id = AccountService.create_account("Oturum", "checking", 10_000.0)
            goal_id = SavingsService.create_goal("Hedef", 1_000.0)
            SavingsService.deposit_to_goal(goal_id, 10.0, account_id)
            SavingsService.withdraw_from_goal(goal_id, 5.0, account_id)
            TransactionService.add_transaction(
                account_id, 25.0, "expense", "Market", "d",
                transaction_date="2026-08-01 10:00:00",
                detect_subscription=False,
            )
            TransactionService.get_transactions_by_period("Bugün")
            AccountService.get_accounts()
        self.assertEqual(ledger.leaked, [])


class ProductionUsesNoNonClosingContextManagerTest(unittest.TestCase):
    """A static guard against the REAL root cause of the descriptor-leak measurement.

    Under the sqlite3 contract, `with get_connection() as conn:` only commits
    or rolls back; it DOES NOT CLOSE. Because the audit harness used exactly
    this pattern it leaked 100 connections over 100 iterations, and we took
    that for a leak in production code. If the pattern creeps back into the
    code base this test breaks.
    """

    SCANNED = ("database", "services", "utils", "widgets",
               "views", "components", "scripts", "tests")

    @staticmethod
    def _is_bare_get_connection(node):
        """`get_connection()` -- WITHOUT a wrapper such as `closing(...)`."""
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if isinstance(func, ast.Name):
            return func.id == "get_connection"
        if isinstance(func, ast.Attribute):
            return func.attr == "get_connection"
        return False

    def test_no_module_uses_get_connection_as_a_context_manager(self):
        """The scan is done over the AST, NOT with a text search.

        A text search also caught mentions in docstrings and error messages --
        a comment EXPLAINING the pattern is not USING it. The AST gives that
        distinction for free and naturally exempts correctly wrapped calls such
        as `closing(get_connection())`.
        """
        offenders = []
        for name in self.SCANNED:
            root = REPO_ROOT / name
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                try:
                    tree = ast.parse(path.read_text(encoding="utf-8"))
                except (SyntaxError, UnicodeDecodeError):
                    continue
                for node in ast.walk(tree):
                    if not isinstance(node, ast.With):
                        continue
                    for item in node.items:
                        if self._is_bare_get_connection(item.context_expr):
                            offenders.append(
                                f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        self.assertEqual(
            offenders, [],
            "`with get_connection() as conn:` KAPATMAZ — bağlantı sızdırır. "
            "`with closing(get_connection()) as conn, conn:` ya da "
            "`managed_connection()` kullan. Sızdıran satırlar: "
            + ", ".join(offenders),
        )

    def test_the_leaking_pattern_really_leaks(self):
        """Proves the prohibition above IS NOT AN EMPTY RULE.

        Saying "do not use it" without showing that the pattern really leaks
        would be unjustified; that is exactly the explanation of the
        descriptor-leak measurement.
        """
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.addCleanup(os.unlink, db_path)
        opened = []
        try:
            with connection_ledger() as ledger:
                for _ in range(10):
                    with sqlite3.connect(db_path) as conn:
                        conn.execute("SELECT 1")
            opened = list(ledger.opened)
            self.assertEqual(len(ledger.opened), 10)
            self.assertEqual(len(ledger.closed), 0,
                             "`with conn:` kapatmamalı — sözleşme bu")
            self.assertEqual(len(ledger.leaked), 10)
        finally:


            for conn in opened:
                try:
                    conn.close()
                except sqlite3.Error:
                    pass
            gc.collect()


if __name__ == "__main__":
    unittest.main()
