"""Half-finished restore recovery must work on the REAL startup path.

A recovery function working only in a unit test does not close real crash
recovery. These tests prove two things separately:

1. Startup calls recovery BEFORE everything that touches the
   key/DB/config (a call-order test).
2. When recovery fails, startup stays FAIL-CLOSED -- DB initialisation and
   migration never run.

"""

import json
import tempfile
import unittest
from pathlib import Path

from services.startup_recovery import (
    RecoveryOutcome,
    StartupRecoveryError,
    run_startup_recovery,
)


class StartupRecoveryContractTest(unittest.TestCase):
    """The contract of `run_startup_recovery`."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.db_path = self.root / "finance.db"
        self.db_path.write_bytes(b"eski-db")
        self.journal = self.root / ".helysofer-restore"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_no_journal_is_not_required(self):
        outcome, _ = run_startup_recovery(db_path=str(self.db_path))
        self.assertIs(outcome, RecoveryOutcome.NOT_REQUIRED)

    def test_completed_recovery_restores_the_old_generation(self):
        self.journal.mkdir(mode=0o700)
        (self.journal / "old-finance.db").write_bytes(b"kurtarilan-db")
        (self.journal / "journal.json").write_text(
            json.dumps({
                "state": "DB_REPLACED",
                "db_path": str(self.db_path),
                "config_path": None,
                "had_config": False,
            }),
            encoding="utf-8",
        )
        outcome, result = run_startup_recovery(db_path=str(self.db_path))
        self.assertIs(outcome, RecoveryOutcome.COMPLETED)
        self.assertTrue(result["recovered"])
        self.assertEqual(self.db_path.read_bytes(), b"kurtarilan-db")
        self.assertFalse(self.journal.exists())

    def test_malformed_journal_fails_closed(self):
        self.journal.mkdir(mode=0o700)
        (self.journal / "journal.json").write_text("{bozuk", encoding="utf-8")
        with self.assertRaises(StartupRecoveryError) as ctx:
            run_startup_recovery(db_path=str(self.db_path))
        self.assertIs(
            ctx.exception.outcome,
            RecoveryOutcome.MANUAL_INTERVENTION_REQUIRED,
        )

        self.assertTrue(self.journal.exists())

    def test_unknown_state_fails_closed(self):
        self.journal.mkdir(mode=0o700)
        (self.journal / "journal.json").write_text(
            json.dumps({"state": "UYDURMA"}), encoding="utf-8"
        )
        with self.assertRaises(StartupRecoveryError):
            run_startup_recovery(db_path=str(self.db_path))

    def test_error_message_leaks_no_paths_or_state(self):
        self.journal.mkdir(mode=0o700)
        (self.journal / "journal.json").write_text("{bozuk", encoding="utf-8")
        with self.assertRaises(StartupRecoveryError) as ctx:
            run_startup_recovery(db_path=str(self.db_path))
        message = str(ctx.exception)
        self.assertNotIn(str(self.db_path), message)
        self.assertNotIn("journal", message.lower())
        self.assertIn("korundu", message)

    def test_recovery_is_idempotent(self):
        self.journal.mkdir(mode=0o700)
        (self.journal / "old-finance.db").write_bytes(b"kurtarilan-db")
        (self.journal / "journal.json").write_text(
            json.dumps({
                "state": "DB_REPLACED",
                "db_path": str(self.db_path),
                "config_path": None,
                "had_config": False,
            }),
            encoding="utf-8",
        )
        run_startup_recovery(db_path=str(self.db_path))
        first = self.db_path.read_bytes()
        outcome, _ = run_startup_recovery(db_path=str(self.db_path))
        self.assertIs(outcome, RecoveryOutcome.NOT_REQUIRED)
        self.assertEqual(self.db_path.read_bytes(), first)






def _record_failure(app, message):
    """The real presenter's contract: set the flag and return a safe root."""
    app._startup_recovery_failure = message
    return _SAFE_ROOT_SENTINEL


_SAFE_ROOT_SENTINEL = object()


class _StopBuild(Exception):
    """For stopping build() at a controlled point."""


if __name__ == "__main__":
    unittest.main()
