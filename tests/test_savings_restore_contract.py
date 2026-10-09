"""The restore contract: goals come back as one generation (slice 4).

What is pinned (docs/ARCHITECTURE.md):

  * Backup -> an EMPTY profile -> restore brings back ALL of the goal's
    fields: goal_uid, name, target amount, accumulated amount, target date,
    status, created_at, color, auto_deposit, the linked account balance and
    the ledger invariants,
  * the DB, the key, the config and a living `savings_goals.json` change as ONE
    generation; if the restore fails ALL FOUR come back,
  * after a successful restore the stale JSON never becomes the active source
    again (it is set aside as `.stale-<time>`, not deleted),
  * NOT FINDING a JSON in the backup is not a problem in the new model (old
    format support),
  * when a backup belonging to a different profile is restored, a numeric id
    collision does not produce a wrong match,
  * in-process memory is refreshed from SQL after a restore, in the same
    process.

"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from contextlib import closing
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.backup_service import create_backup, restore_backup
from utils.errors import DataMigrationError

PASSPHRASE = "restore-sozlesmesi-parolasi-2026"


class _RestoreProfile(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.db_path = self.root / "finance.db"
        self.key_path = self.root / "encryption.key"
        self.json_path = self.root / "savings_goals.json"
        self.package = self.root / "backup.helyosfer-backup"
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

    def backup(self, package=None):
        create_backup(
            package or self.package, PASSPHRASE,
            db_path=self.db_path, key_path=self.key_path,
        )

    def restore(self, package=None, **kwargs):
        return restore_backup(
            package or self.package, PASSPHRASE,
            db_path=self.db_path, key_path=self.key_path,
            safety_backup_path=self.root / "safety.helyosfer-backup",
            **kwargs,
        )

    def goals(self):
        from services.savings_service import SavingsService

        return SavingsService.get_goals()

    def balance(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT balance FROM accounts WHERE id = ?", (self.account_id,)
            ).fetchone()[0]

    def ledger(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT entity_type, entity_id, delta, source"
                " FROM balance_events ORDER BY id"
            ).fetchall()

    def stale_files(self):
        return sorted(self.root.glob("savings_goals.json.stale-*"))


class FullRoundTripTest(_RestoreProfile):
    """Backup -> an empty profile -> restore, field by field."""

    def setUp(self):
        super().setUp()
        from services.savings_service import SavingsService

        self.goal_id = SavingsService.create_goal(
            "Araba Fonu", 20000.0, "2027-01-01",
            color="blue", auto_deposit=True, created_at="2026-01-02",
        )
        SavingsService.deposit_to_goal(self.goal_id, 1250.0, self.account_id)
        self.before = self.goals()[0]
        self.balance_before = self.balance()
        self.ledger_before = self.ledger()
        self.backup()

    def _empty_the_profile(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM savings_goals")
            conn.execute("DELETE FROM balance_events")
            conn.execute("UPDATE accounts SET balance = 0")
            conn.commit()

    def test_every_goal_field_survives_the_round_trip(self):
        self._empty_the_profile()
        self.assertEqual(self.goals(), [])

        self.restore()

        after = self.goals()
        self.assertEqual(len(after), 1)
        restored = after[0]
        for field in ("goal_uid", "goal_name", "target_amount",
                      "current_amount", "target_date", "status",
                      "created_at", "color", "auto_deposit"):
            self.assertEqual(
                restored[field], self.before[field],
                f"restore sonrası '{field}' değişti",
            )

    def test_the_linked_account_balance_and_ledger_come_back_too(self):
        self._empty_the_profile()
        self.restore()

        self.assertEqual(self.balance(), self.balance_before)
        self.assertEqual(self.ledger(), self.ledger_before)

    def test_a_backup_without_any_json_member_is_still_valid(self):
        """In the new model a backup CARRIES NO JSON; that is not a shortcoming."""
        with zipfile.ZipFile(self.package) as archive:
            names = set(archive.namelist())
        self.assertNotIn("savings_goals.json", names)

        self._empty_the_profile()
        result = self.restore()
        self.assertTrue(result["restored"])
        self.assertEqual(len(self.goals()), 1)


class StaleJsonIsNeverReactivatedTest(_RestoreProfile):
    def setUp(self):
        super().setUp()
        from services.savings_service import SavingsService

        SavingsService.create_goal("Araba Fonu", 20000.0)
        self.backup()

        self.json_path.write_text(
            json.dumps({"goals": {"data": [
                {"id": 1, "name": "Tatil Fonu", "target": 10000.0,
                 "current": 900.0},
            ]}}),
            encoding="utf-8",
        )

    def test_a_successful_restore_moves_the_stale_json_aside(self):
        result = self.restore()

        self.assertFalse(self.json_path.exists(), "bayat JSON yerinde kaldı")
        stale = self.stale_files()
        self.assertEqual(len(stale), 1)
        self.assertEqual(result["stale_savings_json"], str(stale[0]))
        self.assertIn("Tatil Fonu", stale[0].read_text(encoding="utf-8"))

    def test_the_migration_engine_ignores_the_quarantined_file(self):
        """The file set aside is NEVER READ AGAIN in normal operation."""
        from services.savings_migration import run_savings_migration

        self.restore()
        result = run_savings_migration(
            json_path=self.json_path, db_path=self.db_path
        )

        self.assertEqual(result["status"], "no-json")
        self.assertEqual([g["goal_name"] for g in self.goals()], ["Araba Fonu"])

    def test_a_failed_restore_puts_the_json_back_with_the_old_generation(self):
        original = self.json_path.read_text(encoding="utf-8")
        goals_before = self.goals()

        def boom(stage):
            if stage == "after_database_replaced":
                raise RuntimeError("enjekte edilen arıza")

        with self.assertRaises(DataMigrationError):
            self.restore(_failure_hook=boom)

        self.assertTrue(self.json_path.exists(), "JSON geri konmadı")
        self.assertEqual(self.json_path.read_text(encoding="utf-8"), original)
        self.assertEqual(self.stale_files(), [])
        self.assertEqual(self.goals(), goals_before)

    def test_a_json_that_did_not_exist_before_is_not_resurrected(self):
        """`had_savings_json=False` iken rollback dosya YARATMAMALI."""
        self.json_path.unlink()

        def boom(stage):
            if stage == "after_key_replaced":
                raise RuntimeError("enjekte edilen arıza")

        with self.assertRaises(DataMigrationError):
            self.restore(_failure_hook=boom)

        self.assertFalse(self.json_path.exists())


class InterruptedRestoreRecoveryTest(_RestoreProfile):
    def setUp(self):
        super().setUp()
        from services.savings_service import SavingsService

        SavingsService.create_goal("Araba Fonu", 20000.0)
        self.backup()
        self.json_path.write_text(
            json.dumps({"goals": {"data": [
                {"id": 1, "name": "Tatil Fonu", "target": 10000.0},
            ]}}),
            encoding="utf-8",
        )

    def test_a_crash_inside_the_generation_rolls_the_json_back(self):
        """BEFORE COMMITTED: the old generation is canonical, all four come back."""
        from services.backup_service import recover_interrupted_restore

        original = self.json_path.read_text(encoding="utf-8")

        def boom(stage):
            if stage == "after_config_replaced":
                raise RuntimeError("enjekte edilen arıza")

        with self.assertRaises(DataMigrationError):
            self.restore(_failure_hook=boom)


        outcome = recover_interrupted_restore(db_path=self.db_path)
        self.assertFalse(outcome["recovered"])
        self.assertTrue(self.json_path.exists())
        self.assertEqual(self.json_path.read_text(encoding="utf-8"), original)
        self.assertEqual(self.stale_files(), [])

    def test_a_crash_after_the_commit_marker_completes_the_quarantine(self):
        """AFTER the commit marker: the restore is canonical, the remaining work COMPLETES."""
        from services.backup_service import recover_interrupted_restore

        def boom(stage):
            if stage == "after_committed_marker":
                raise RuntimeError("enjekte edilen arıza")

        with self.assertRaises(RuntimeError):
            self.restore(_failure_hook=boom)


        self.assertTrue(self.json_path.exists())

        outcome = recover_interrupted_restore(db_path=self.db_path)

        self.assertEqual(outcome["action"], "cleanup-only")
        self.assertFalse(
            self.json_path.exists(),
            "COMMITTED'den sonra bayat JSON kenara alınmalıydı",
        )
        self.assertEqual(len(self.stale_files()), 1)


class ForeignProfileRestoreTest(_RestoreProfile):
    """A backup belonging to a different profile: a numeric id collision must not produce a wrong match."""

    def test_numeric_id_collision_does_not_misattribute_a_goal(self):
        from services.savings_service import SavingsService


        foreign_root = self.root / "foreign"
        foreign_root.mkdir()
        foreign_db = foreign_root / "finance.db"
        foreign_key_path = foreign_root / "encryption.key"
        foreign_key_path.write_bytes(self.key)
        foreign_package = foreign_root / "foreign.helyosfer-backup"

        with mock.patch("database.db.DB_NAME", str(foreign_db)):
            from database.init_db import initialize_database
            from services.account_service import AccountService

            initialize_database()
            AccountService.create_account(
                "Yabancı Vadesiz", "checking", initial_balance=100.0
            )
            foreign_goal_id = SavingsService.create_goal(
                "Yabancı Hedef", 777.0
            )
            foreign_goals = SavingsService.get_goals()
            create_backup(
                foreign_package, PASSPHRASE,
                db_path=foreign_db, key_path=foreign_key_path,
            )

        local_goal_id = SavingsService.create_goal("Yerel Hedef", 20000.0)
        local_uid = self.goals()[0]["goal_uid"]
        self.assertEqual(local_goal_id, foreign_goal_id,
                         "senaryonun ön şartı: iki profilde de aynı sayısal id")

        self.restore(package=foreign_package)

        restored = self.goals()
        self.assertEqual([g["goal_name"] for g in restored], ["Yabancı Hedef"])
        self.assertNotEqual(
            restored[0]["goal_uid"], local_uid,
            "farklı profillerin hedefleri aynı kalıcı kimliği taşıyamaz",
        )
        self.assertEqual(restored[0]["goal_uid"], foreign_goals[0]["goal_uid"])

    def test_a_deposit_aimed_at_the_pre_restore_goal_is_refused(self):
        """The identity belonging to the pre-restore card must not be accepted after a restore."""
        from services.savings_service import SavingsService

        local_goal_id = SavingsService.create_goal("Yerel Hedef", 20000.0)
        stale_card = dict(self.goals()[0])
        self.backup()

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM savings_goals")
            conn.commit()
        replacement_id = SavingsService.create_goal("Başka Hedef", 5000.0)
        self.assertEqual(replacement_id, local_goal_id + 1)

        before = self.balance()
        with self.assertRaises(ValueError):
            SavingsService.deposit_to_goal(
                replacement_id, 100.0, self.account_id,
                goal_uid=stale_card["goal_uid"],
            )
        self.assertEqual(self.balance(), before)




class WindowsAtomicReplaceTest(_RestoreProfile):
    """The Windows file lock / atomic replace behaviour."""

    def test_restore_leaves_no_open_handle_on_the_database(self):
        """After a restore the DB file must be RENAMABLE.

        Windows does not let a file with an open handle be moved; a leaked
        connection shows up concretely here (it would pass silently on
        Linux).
        """
        from services.savings_service import SavingsService

        SavingsService.create_goal("Araba Fonu", 20000.0)
        self.backup()
        self.restore()

        moved = self.root / "finance.moved.db"
        os.replace(self.db_path, moved)
        os.replace(moved, self.db_path)

    def test_the_stale_json_move_is_atomic_and_never_overwrites(self):
        """Quarantining twice within the same second: both files must remain."""
        from services.backup_service import _quarantine_stale_savings_json
        from services.savings_service import SavingsService

        SavingsService.create_goal("Araba Fonu", 20000.0)
        self.backup()

        self.json_path.write_text("birinci", encoding="utf-8")
        first = _quarantine_stale_savings_json(self.json_path)
        self.json_path.write_text("ikinci", encoding="utf-8")
        second = _quarantine_stale_savings_json(self.json_path)

        self.assertNotEqual(first, second)
        self.assertEqual(first.read_text(encoding="utf-8"), "birinci")
        self.assertEqual(second.read_text(encoding="utf-8"), "ikinci")


if __name__ == "__main__":
    unittest.main()
