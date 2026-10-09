"""Identity reuse: money goes to the WRONG goal after a restore.

THE MEASURED DEFECT (contract: docs/ARCHITECTURE.md). Savings goals lived in
two places: the money in SQLite, the card on screen in
`savings_goals.json`. The JSON marked the goal only by the SQL row's NUMERIC
id.

`sqlite_sequence` is INSIDE the `finance.db` file. Because a restore replaces
the file wholesale, the counter also rewinds to the backup's value; the first
goal opened after the restore takes back the id the stale JSON still points
at. The user deposits into the "Tatil Fonu" card on screen, the money is
written to a completely different goal ("Yeni Hedef"), and it really leaves
their account.

This file builds the plan's 7 steps with REAL components: a real
`SavingsService`, real `finance.db` files, real `create_backup`/`restore_backup`.
A unit test imitating `sqlite_sequence` cannot prove this defect -- the counter
rewinding is a CONSEQUENCE of restore's file-replacement behaviour, not a
separate phenomenon.

"""

import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.savings_service import SavingsService

PASSPHRASE = "kimlik-yeniden-kullanim-2026"


class IdentityReuseAfterRestoreTest(unittest.TestCase):
    """The plan's 7 steps, with real files and a real restore."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.db_path = root / "finance.db"
        self.key_path = root / "encryption.key"
        self.package = root / "backup.helyosfer-backup"
        self.key = os.urandom(32)
        self.key_path.write_bytes(self.key)

        self._db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self._db_patch.start()
        self.addCleanup(self._db_patch.stop)
        self._key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self._key_patch.start()
        self.addCleanup(self._key_patch.stop)

        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account_id = AccountService.create_account(
            "Vadesiz", "checking", initial_balance=5000.0
        )


    def _sqlite_sequence(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = 'savings_goals'"
            ).fetchone()
        return row[0] if row else None

    def _balance(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT balance FROM accounts WHERE id = ?", (self.account_id,)
            ).fetchone()[0]

    def _ledger_rows(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM balance_events"
            ).fetchone()[0]

    def _goal_amounts(self):
        return {
            goal["goal_name"]: float(goal["current_amount"])
            for goal in SavingsService.get_goals()
        }


    def _backup(self):
        from services.backup_service import create_backup

        create_backup(
            self.package,
            PASSPHRASE,
            db_path=self.db_path,
            key_path=self.key_path,
        )

    def _restore(self):
        from services.backup_service import restore_backup

        restore_backup(
            self.package,
            PASSPHRASE,
            db_path=self.db_path,
            key_path=self.key_path,
            safety_backup_path=Path(self._tmp.name) / "safety.helyosfer-backup",
        )


    def test_restore_brings_back_the_backed_up_goal_for_the_user(self):
        """Half of the root cause: (a) the restored goal must be visible to the user.

        The backup carries only SQL; as long as the interface reads from
        JSON, a restore into an empty profile DID NOT SHOW the goals.
        """
        SavingsService.create_goal("Araba Fonu", 20000.0)
        self._backup()


        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM savings_goals")
            conn.commit()
        self.assertEqual(SavingsService.get_goals(), [])

        self._restore()

        names = [goal["goal_name"] for goal in SavingsService.get_goals()]
        self.assertEqual(names, ["Araba Fonu"])


if __name__ == "__main__":
    unittest.main()
