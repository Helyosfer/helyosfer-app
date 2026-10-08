"""CSV export must work on Windows too.

THE FINDING: while protecting the plaintext CSV export with POSIX permissions,
the code called `os.fchmod`. That call DOES NOT EXIST ON WINDOWS -- an
`AttributeError` is raised and the export does not work at all. On top of that
the cleanup path gives `PermissionError [WinError 32]` because of the open fd,
so the user cannot even see the real error. Because development was done on
Linux, the fix itself had introduced a regression, and it surfaced on the first
real Windows CI run.

The tests here SIMULATE Windows (by removing the `os.fchmod` attribute), so the
guard is pinned on Linux too and never turns back into a path that blows up
only on Windows.

"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock


class _Profile(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.addCleanup(
            lambda: os.path.exists(self.db_path) and os.unlink(self.db_path)
        )
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account_id = AccountService.create_account("CSV", "checking", 500.0)
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            self.account_id, 25.0, "expense", "Market", "alışveriş",
            transaction_date="2026-08-01 10:00:00", detect_subscription=False,
        )

    def _export_dir(self):
        directory = tempfile.mkdtemp()


        self.addCleanup(shutil.rmtree, directory, ignore_errors=True)
        return Path(directory)


class ExportWorksWithoutFchmodTest(_Profile):
    """The export MUST WORK when `os.fchmod` is absent (Windows)."""

    @unittest.skipUnless(hasattr(os, "fchmod"),
                         "zaten fchmod'suz platform — simülasyona gerek yok")
    def test_export_succeeds_when_fchmod_is_unavailable(self):
        from services.migration_service import export_all_to_csv

        target = self._export_dir() / "disari.csv"
        saved = os.fchmod
        del os.fchmod
        try:
            self.assertFalse(hasattr(os, "fchmod"), "simülasyon kurulmadı")
            path, count = export_all_to_csv(target)
        finally:
            os.fchmod = saved
        self.assertTrue(Path(path).exists(), "CSV yazılmadı")
        self.assertGreater(count, 0)
        content = Path(path).read_text(encoding="utf-8-sig")
        self.assertIn("Market", content)

    def test_no_staging_file_is_left_behind(self):
        """No `.helysofer-export-*` may be left behind after a successful export."""
        from services.migration_service import export_all_to_csv

        directory = self._export_dir()
        export_all_to_csv(directory / "disari.csv")
        leftovers = list(directory.glob(".helysofer-export-*"))
        self.assertEqual(leftovers, [], f"staging dosyası kaldı: {leftovers}")


class CleanupClosesTheDescriptorTest(_Profile):
    """The fd must be closed on the error path, or Windows will not let the file be deleted."""

    def test_staging_file_is_removed_when_writing_fails(self):
        from services import migration_service

        directory = self._export_dir()
        target = directory / "disari.csv"

        class _Boom(Exception):
            pass


        with mock.patch.object(migration_service.os, "fdopen",
                               side_effect=_Boom("yazma açılamadı")):
            with self.assertRaises(_Boom):
                migration_service.export_all_to_csv(target)

        leftovers = list(directory.glob(".helysofer-export-*"))
        self.assertEqual(leftovers, [], f"staging dosyası kaldı: {leftovers}")
        self.assertFalse(target.exists(), "yarım hedef dosya oluştu")

    def test_descriptor_is_closed_before_unlink(self):
        """Verifies the contract INDEPENDENTLY OF THE PLATFORM.

        The test above stays green on Linux BECAUSE Linux lets an open file be
        deleted -- so removing `os.close` there makes no difference. Windows
        shows the difference, but so that the fix is preserved on Linux too the
        `close` call itself is measured here: it is the only
        platform-independent evidence that the deletion order is right.
        """
        from services import migration_service

        directory = self._export_dir()

        class _Boom(Exception):
            pass

        closed = []
        real_close = migration_service.os.close

        def _tracking_close(fd):
            closed.append(fd)
            return real_close(fd)

        with mock.patch.object(migration_service.os, "fdopen",
                               side_effect=_Boom("yazma açılamadı")):
            with mock.patch.object(migration_service.os, "close",
                                   side_effect=_tracking_close):
                with self.assertRaises(_Boom):
                    migration_service.export_all_to_csv(directory / "disari.csv")

        self.assertEqual(
            len(closed), 1,
            "hata yolunda descriptor kapatılmadı — Windows'ta staging dosyası "
            "silinemez ve şifresi çözülmüş veri diskte kalır",
        )


@unittest.skipUnless(hasattr(os, "fchmod"), "POSIX izin bitleri gerekiyor")
class PosixPermissionsAreStillAppliedTest(_Profile):
    """On POSIX the protection stands UNCHANGED -- the fix must not loosen it."""

    def test_exported_file_is_owner_only(self):
        from services.migration_service import export_all_to_csv

        path, _ = export_all_to_csv(self._export_dir() / "disari.csv")
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o600, f"beklenen 0600, bulunan {oct(mode)}")


if __name__ == "__main__":
    unittest.main()
