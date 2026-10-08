"""A migration must be able to complete what is missing after an interruption.

The finding: `ALTER TABLE` is persistent, but the backfill was INSIDE
that `if column not in cols` block. If the backfill blew up, the next startup
saw the column as PRESENT and never entered the block, and `account_type`
stayed permanently NULL.

The column's existence is no longer taken as proof of completion; the backfill
looks at its own postcondition ("is there a row not backfilled?").

"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock


class _FaultCursor:
    """A cursor wrapper that raises once on a particular SQL fragment."""

    def __init__(self, inner, trigger):
        self._inner = inner
        self._trigger = trigger
        self._fired = False

    def execute(self, sql, *args, **kwargs):
        if not self._fired and self._trigger in sql:
            self._fired = True
            raise OSError(f"injected during: {self._trigger}")
        return self._inner.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _FaultConnection:
    """An `sqlite3.Connection` wrapper -- because the `cursor` attribute is
    read-only it cannot be patched directly.
    """

    def __init__(self, inner, trigger):
        self._inner = inner
        self._trigger = trigger

    def cursor(self):
        return _FaultCursor(self._inner.cursor(), self._trigger)

    def __enter__(self):
        return self._inner.__enter__()

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class MigrationRetrySafetyTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _legacy_database(self):
        """Sets up an old schema WITHOUT the account_type column."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE accounts ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name TEXT NOT NULL, type TEXT NOT NULL, "
                "balance REAL DEFAULT 0)"
            )
            conn.execute(
                "INSERT INTO accounts (name, type, balance) "
                "VALUES ('Eski Kart', 'credit', -500.0)"
            )
            conn.execute(
                "INSERT INTO accounts (name, type, balance) "
                "VALUES ('Eski Vadesiz', 'bank', 1500.0)"
            )
            conn.commit()

    def _account_types(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return [
                row[0] for row in conn.execute(
                    "SELECT account_type FROM accounts ORDER BY id"
                )
            ]

    def _has_column(self, name):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return name in {
                row[1] for row in conn.execute("PRAGMA table_info(accounts)")
            }

    def test_backfill_resumes_after_the_alter_survived_a_crash(self):
        """If the ALTER persisted and the backfill blew up, the next startup must complete it."""
        from database.init_db import initialize_database

        self._legacy_database()

        real_connect = sqlite3.connect

        def _faulty_connect(*args, **kwargs):
            return _FaultConnection(
                real_connect(*args, **kwargs), "SET account_type = CASE"
            )

        with mock.patch("sqlite3.connect", _faulty_connect):
            with self.assertRaises(OSError):
                initialize_database()


        self.assertTrue(
            self._has_column("account_type"),
            "test kurulumu ALTER'ı uygulayamadı; vaka geçersiz",
        )
        self.assertEqual(
            self._account_types(), [None, None],
            "test kurulumu backfill'i durduramadı; vaka geçersiz",
        )


        initialize_database()
        self.assertEqual(self._account_types(), ["credit_card", "checking"])

    def test_backfill_is_idempotent_on_a_healthy_database(self):
        """On a healthy database a second startup must change nothing."""
        from database.init_db import initialize_database

        self._legacy_database()
        initialize_database()
        first = self._account_types()
        initialize_database()
        self.assertEqual(self._account_types(), first)
        self.assertEqual(first, ["credit_card", "checking"])

    def test_manually_blanked_account_type_is_repaired(self):
        """An empty string must count as missing too, not only NULL."""
        from database.init_db import initialize_database

        self._legacy_database()
        initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE accounts SET account_type = '' WHERE id = 1")
            conn.commit()

        initialize_database()
        self.assertEqual(self._account_types(), ["credit_card", "checking"])

    def test_credit_limit_backfill_also_resumes(self):
        """The same pattern must hold for `credit_limit`."""
        from database.init_db import initialize_database

        self._legacy_database()
        initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("UPDATE accounts SET credit_limit = NULL")
            conn.commit()

        initialize_database()
        with closing(sqlite3.connect(self.db_path)) as conn:
            limits = [
                row[0] for row in conn.execute(
                    "SELECT credit_limit FROM accounts ORDER BY id"
                )
            ]
        self.assertEqual(limits, [0, 0])


if __name__ == "__main__":
    unittest.main()
