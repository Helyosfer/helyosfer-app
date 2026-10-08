"""`transactions.account_id -> accounts.id` must REALLY be enforced.

THE MEASURED DEFECT: the constraint sat in the schema but did nothing. In
SQLite, foreign-key enforcement is PER CONNECTION and OFF BY DEFAULT (a
backward-compatibility decision, so since 3.6.19). The measurement:

    >>> conn = get_connection()
    >>> conn.execute("PRAGMA foreign_keys").fetchone()[0]
    0
    >>> conn.execute("INSERT INTO transactions (account_id, ...) VALUES (999999, ...)")

    >>> conn.execute("PRAGMA foreign_key_check").fetchall()
    [<violation>]

So writing a transaction against a non-existent account was allowed while the
schema believed it had forbidden it. An orphan transaction means money that is
tied to no account's balance yet appears in the reports.

FAIL-CLOSED: existing orphan records are NOT SILENTLY DELETED, are NOT
ATTACHED to another account, and the financial history is not rewritten.
Startup stops and says which row of which table lost which parent; the user
makes the decision.

"""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from utils.errors import FinancialDataIntegrityError

_TX_INSERT = (
    "INSERT INTO transactions "
    "(account_id, amount, type, category, description, transaction_date) "
    "VALUES (?, ?, ?, ?, ?, ?)"
)


class ForeignKeyEnforcementTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "finance.db"
        self.key = os.urandom(32)
        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database

        initialize_database()

    def test_every_connection_has_foreign_keys_on(self):
        from database.db import get_connection

        with closing(get_connection()) as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_managed_connection_inherits_the_same_guarantee(self):
        from database.db import managed_connection

        with managed_connection() as conn:
            self.assertEqual(conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_transaction_for_a_missing_account_is_refused(self):
        from database.db import get_connection

        with closing(get_connection()) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute(
                    _TX_INSERT,
                    (999999, "x", "expense", "Test", "y", "2026-01-01 00:00:00"),
                )
                conn.commit()

    def test_deleting_an_account_with_transactions_is_refused(self):
        """Deleting a parent before its children no longer passes silently."""
        from database.db import get_connection
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account(
            "Silme Hesabı", "checking", initial_balance=500
        )
        TransactionService.add_transaction(
            account_id, 10.0, "expense", "Market", "test"
        )
        with closing(get_connection()) as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
                conn.commit()

    def test_normal_account_and_transaction_lifecycle_still_works(self):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account(
            "Normal Hesap", "checking", initial_balance=1000
        )
        TransactionService.add_transaction(
            account_id, 250.0, "expense", "Market", "alışveriş"
        )
        TransactionService.add_transaction(
            account_id, 100.0, "income", "Maaş", "ek gelir"
        )
        self.assertAlmostEqual(
            AccountService.get_account(account_id)["balance"], 850.0
        )

    def test_credit_card_deletion_is_still_atomic_with_enforcement_on(self):
        """`delete_credit_card` deletes the children BEFORE the parent; the order is right."""
        from database.db import get_connection
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        card_id = AccountService.create_account(
            "Kart", "credit_card", initial_balance=0, credit_limit=10000
        )
        TransactionService.add_transaction(
            card_id, 300.0, "expense", "Market", "kart harcaması"
        )
        AccountService.delete_credit_card(card_id)

        with closing(get_connection()) as conn:
            self.assertIsNone(
                conn.execute(
                    "SELECT id FROM accounts WHERE id = ?", (card_id,)
                ).fetchone()
            )
            self.assertEqual(
                conn.execute(
                    "SELECT COUNT(*) FROM transactions WHERE account_id = ?",
                    (card_id,),
                ).fetchone()[0],
                0,
            )
            self.assertEqual(
                conn.execute("PRAGMA foreign_key_check").fetchall(), []
            )


class FullResetWithEnforcementTest(unittest.TestCase):
    """A full data wipe must work with enforcement on too.

    The full reset deletes the tables in `sqlite_master` order, and
    that order brings `accounts` BEFORE `transactions`. With enforcement on,
    that loop failed with `FOREIGN KEY constraint failed` -- measured. This test
    repeats that order exactly and pins the `PRAGMA defer_foreign_keys`
    solution.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "finance.db"
        self.key = os.urandom(32)
        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        initialize_database()
        account_id = AccountService.create_account(
            "Sıfırlanacak", "checking", initial_balance=1000
        )
        TransactionService.add_transaction(
            account_id, 50.0, "expense", "Market", "silinecek"
        )

    def test_wiping_every_table_in_schema_order_still_commits(self):
        from database.db import managed_connection

        with managed_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("BEGIN")
            cursor.execute("PRAGMA defer_foreign_keys = ON")
            cursor.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
            names = [row["name"] for row in cursor.fetchall()]
            self.assertLess(names.index("accounts"), names.index("transactions"))
            for name in names:
                cursor.execute(f'DELETE FROM "{name.replace(chr(34), chr(34) * 2)}"')
            cursor.execute("DELETE FROM sqlite_sequence")
            conn.commit()

        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], 0
            )
            self.assertEqual(
                conn.execute("PRAGMA foreign_key_check").fetchall(), []
            )

    def test_deferred_enforcement_still_refuses_a_genuinely_broken_commit(self):
        """Deferring DOES NOT DISABLE enforcement: if there is an inconsistency at commit it is refused."""
        from database.db import managed_connection

        with self.assertRaises(sqlite3.IntegrityError):
            with managed_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("BEGIN")
                cursor.execute("PRAGMA defer_foreign_keys = ON")
                cursor.execute(
                    _TX_INSERT,
                    (555555, "x", "expense", "T", "y", "2026-01-01 00:00:00"),
                )
                conn.commit()


class OrphanedLegacyDatabaseTest(unittest.TestCase):
    """Old profiles written without the constraint enforced must be fail-closed."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "finance.db"
        self.key = os.urandom(32)
        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database

        initialize_database()

    def _inject_orphan(self):
        """Writes an orphan row with a raw connection that has FK enforcement OFF.

        Exactly what the old version did -- which is why bare
        `sqlite3.connect` is used rather than `get_connection`.
        """
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                _TX_INSERT,
                (424242, "x", "expense", "Eski", "öksüz", "2026-01-01 00:00:00"),
            )
            conn.commit()

    def test_orphaned_rows_stop_startup_instead_of_being_repaired(self):
        from database.init_db import initialize_database

        self._inject_orphan()
        with closing(sqlite3.connect(self.db_path)) as conn:
            before = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE account_id = ?",
                (424242,),
            ).fetchone()[0]
        self.assertEqual(before, 1)

        with self.assertRaises(FinancialDataIntegrityError) as caught:
            initialize_database()


        message = str(caught.exception)
        self.assertIn("transactions", message)
        self.assertIn("accounts", str(caught.exception.reason))


        with closing(sqlite3.connect(self.db_path)) as conn:
            after = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE account_id = ?",
                (424242,),
            ).fetchone()[0]
        self.assertEqual(after, 1)

    def test_a_clean_database_upgrades_without_complaint(self):
        from database.init_db import initialize_database
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account(
            "Temiz", "checking", initial_balance=100
        )
        TransactionService.add_transaction(
            account_id, 10.0, "expense", "Market", "temiz"
        )
        initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            self.assertEqual(
                conn.execute("PRAGMA foreign_key_check").fetchall(), []
            )


class BackupRefusesOrphanedDatabaseTest(unittest.TestCase):
    """A violation in the database to be restored must be caught BEFORE the restore."""

    PASSPHRASE = "test-kurtarma-parolasi-2026"

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "finance.db"
        self.key_path = root / "encryption.key"
        self.package = root / "backup.helysofer-backup"
        self.key = os.urandom(32)
        self.key_path.write_bytes(self.key)
        os.chmod(self.key_path, 0o600)

        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        initialize_database()
        self.account_id = AccountService.create_account(
            "Yedek", "checking", initial_balance=1000
        )
        TransactionService.add_transaction(
            self.account_id, 125.50, "expense", "Market", "açıklama"
        )

    def test_a_package_holding_orphaned_rows_is_refused(self):
        from services.backup_service import create_backup
        from utils.errors import IntegrityVerificationError

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                _TX_INSERT,
                (777777, "x", "expense", "Eski", "öksüz", "2026-01-01 00:00:00"),
            )
            conn.commit()

        with self.assertRaises(IntegrityVerificationError):
            create_backup(
                self.package,
                self.PASSPHRASE,
                db_path=self.db_path,
                key_path=self.key_path,
            )

    def test_a_clean_package_still_verifies(self):
        from services.backup_service import create_backup, verify_backup

        create_backup(
            self.package,
            self.PASSPHRASE,
            db_path=self.db_path,
            key_path=self.key_path,
        )
        self.assertEqual(
            verify_backup(self.package, self.PASSPHRASE)["key"], self.key
        )


if __name__ == "__main__":
    unittest.main()
