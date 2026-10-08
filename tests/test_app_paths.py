"""Verifies the path resolution and the
one-off file-move mechanics of `utils/app_paths.py` -- none of it depends on the
GUI, and it is tested by monkeypatching the environment variables platformdirs
itself reads (XDG_DATA_HOME and so on, on Linux), with no need for a real OS
installation.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

from utils.app_paths import cache_dir, data_dir, log_dir, migrate_legacy_path, resource_dir


class PathResolutionTest(unittest.TestCase):
    """platformdirs itself is an already-tested library -- what is verified here
    is that OUR wrapper really does delegate to platformdirs and returns three
    DIFFERENT, mutually disjoint directories for the three purposes
    (data/cache/log).
    """

    def test_import_alone_creates_no_directories(self):
        """Merely importing the module or calling the functions must create no real
        directory -- the test suite leaving no side effect in the developer's
        real home directory on every import depends on this.
        """
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = os.path.join(tmp, "xdg-probe")
            with mock.patch.dict(
                os.environ,
                {"XDG_DATA_HOME": fake_home, "XDG_CACHE_HOME": fake_home, "XDG_STATE_HOME": fake_home},
            ):
                data_dir()
                cache_dir()
                log_dir()
            self.assertFalse(os.path.exists(fake_home))

    @staticmethod
    def _home_override(root):
        """The PLATFORM-INDEPENDENT redirection that pulls the paths into the sandbox.

        This used to have only XDG_* in it. XDG DOES NOT WORK on Windows:
        `platformdirs` never looks at the environment variables there and calls
        `SHGetFolderPathW` through `ctypes`. So this test was green on Linux
        while HIDING the fact that the path redirection was entirely broken on
        Windows -- and the test suite's own isolation rested on the same broken
        mechanism. `HELYSOFER_HOME` (utils/app_paths.py) is valid on every
        platform.
        """
        return {"HELYSOFER_HOME": root}

    def test_data_cache_log_dirs_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ,
                self._home_override(tmp),
            ):
                d, c, log = data_dir(), cache_dir(), log_dir()


            self.assertNotEqual(d, c)
            self.assertNotEqual(d, log)
            self.assertNotEqual(c, log)
            for resolved in (d, c, log):
                self.assertTrue(
                    resolved.startswith(tmp),
                    f"{resolved!r} sandbox {tmp!r} altında değil — bu "
                    "platformda yol yönlendirmesi ÇALIŞMIYOR demektir.",
                )

    @unittest.skipIf(
        os.name == "nt",
        "platformdirs Windows'ta ortam değişkenlerini yok sayar (ctypes ile "
        "SHGetFolderPathW); bu test XDG üzerinden VARSAYILAN çözümlemeyi "
        "sınıyor ve orada yönlendirilemez.",
    )
    def test_resolved_dirs_are_namespaced_under_the_app_name(self):
        """DEFAULT (unredirected) resolution must be namespaced by the application name.

        `HELYSOFER_HOME` is cleared EXPLICITLY here: this test exercises
        platformdirs' default behaviour, not the override path. The test suite
        sets that variable globally for its own isolation (run_tests.py) --
        without clearing it we would be measuring the wrong code path here.
        """
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(
                os.environ, {"XDG_DATA_HOME": tmp, "HELYSOFER_HOME": ""}
            ):
                d = data_dir()
            self.assertIn("Helysofer", d)

    def test_home_override_wins_over_platform_defaults(self):
        """`HELYSOFER_HOME` must redirect the resolution on every platform.

        This is the contract the test suite's isolation rests on; if it breaks,
        the tests start writing into the developer's REAL data directory.
        """
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {"HELYSOFER_HOME": tmp}):
                self.assertTrue(data_dir().startswith(tmp))
                self.assertTrue(cache_dir().startswith(tmp))
                self.assertTrue(log_dir().startswith(tmp))


class ResourceDirTest(unittest.TestCase):
    """The function that closes the root cause of the crash produced empirically
    on a real Windows installation (a `FileNotFoundError` for a bundled file).

    Startup calls `os.chdir(resource_dir())` -- which depends
    on `resource_dir()` returning the right directory in BOTH the PACKAGED
    (sys.frozen) and the DEVELOPMENT modes. `sys.frozen`/`sys._MEIPASS` are
    attributes PyInstaller really sets while a packaged .exe runs -- they are
    imitated here without a real .exe (which is not possible on Linux).
    """

    def test_dev_mode_resolves_to_the_repo_root(self):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.assertEqual(resource_dir(), repo_root)

        self.assertTrue(os.path.isdir(os.path.join(resource_dir(), "ui")))

    def test_frozen_mode_resolves_to_sys_meipass_not_cwd_or_file(self):
        """PyInstaller's own mechanism: in a packaged build `sys.frozen = True`
        and `sys._MEIPASS` points at the directory where the files embedded
        with `datas=[...]` REALLY sit -- which can be DIFFERENT from the .exe's
        own directory (PyInstaller 6.x's `_internal` subfolder). To prove that trusting `__file__` or `os.getcwd()`
        would be WRONG, both are left DIFFERENT from the real value.
        """
        fake_meipass = "/some/fake/pyinstaller/bundle/dir"
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sys, "_MEIPASS", fake_meipass, create=True):
            self.assertEqual(resource_dir(), fake_meipass)

    def test_frozen_flag_absent_means_dev_mode_even_if_meipass_lingers(self):
        """As long as `sys.frozen` really is False or absent (the state of a real
        development environment), `sys._MEIPASS` must be ignored even if it has
        lingered in the environment for whatever reason.
        """
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with mock.patch.object(sys, "_MEIPASS", "/leftover/stale/path", create=True):
            self.assertEqual(resource_dir(), repo_root)


class MigrateLegacyPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old_path = os.path.join(self.tmp.name, "old", "finance.db")
        self.new_path = os.path.join(self.tmp.name, "new", "finance.db")
        os.makedirs(os.path.dirname(self.old_path))

    def _write(self, path, content):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_moves_old_file_to_new_location(self):
        self._write(self.old_path, "gercek kullanici verisi")
        moved = migrate_legacy_path(self.old_path, self.new_path)
        self.assertTrue(moved)
        self.assertFalse(os.path.exists(self.old_path))
        with open(self.new_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "gercek kullanici verisi")

    def test_creates_missing_parent_directory_of_new_path(self):
        self._write(self.old_path, "veri")
        nested_new = os.path.join(self.tmp.name, "a", "b", "c", "finance.db")
        self.assertTrue(migrate_legacy_path(self.old_path, nested_new))
        self.assertTrue(os.path.exists(nested_new))

    def test_fresh_install_with_no_legacy_file_does_nothing(self):
        moved = migrate_legacy_path(self.old_path, self.new_path)
        self.assertFalse(moved)
        self.assertFalse(os.path.exists(self.new_path))

    def test_never_overwrites_an_existing_new_location(self):
        """The most critical behaviour: if there is already a (current) file at the
        target, the stale copy at the old location must NOT be written OVER it
        -- that is where user data loss comes from.
        """
        self._write(self.old_path, "eski/bayat veri")
        self._write(self.new_path, "guncel veri")
        moved = migrate_legacy_path(self.old_path, self.new_path)
        self.assertFalse(moved)
        with open(self.new_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "guncel veri")

        self.assertTrue(os.path.exists(self.old_path))

    def test_survives_a_read_only_source_directory(self):
        """This function's REAL use case: the source is the application install
        directory, which on a packaged Windows installation is usually
        READ-ONLY -- the reason item 4 exists. The first version used
        `shutil.move` here; move falls back to `os.rename` on the same
        filesystem and requires write permission IN THE SOURCE DIRECTORY, so it
        raised PermissionError, and because build() did not catch it the
        application died without ever opening. The data must still reach the
        new location.
        """
        self._write(self.old_path, "salt okunur dizindeki veri")
        old_dir = os.path.dirname(self.old_path)
        os.chmod(old_dir, 0o555)
        self.addCleanup(os.chmod, old_dir, 0o755)

        moved = migrate_legacy_path(self.old_path, self.new_path)

        self.assertTrue(moved)
        with open(self.new_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "salt okunur dizindeki veri")

    def test_undeletable_source_is_not_recopied_on_the_next_run(self):
        """On a read-only source the old file stays undeleted; that is ACCEPTABLE,
        but at the next startup it must not be copied over the data the user
        has current at that moment.
        """
        self._write(self.old_path, "eski veri")
        old_dir = os.path.dirname(self.old_path)
        os.chmod(old_dir, 0o555)
        self.addCleanup(os.chmod, old_dir, 0o755)

        self.assertTrue(migrate_legacy_path(self.old_path, self.new_path))

        with open(self.new_path, "w", encoding="utf-8") as f:
            f.write("kullanicinin guncel verisi")

        self.assertFalse(migrate_legacy_path(self.old_path, self.new_path))
        with open(self.new_path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "kullanicinin guncel verisi")

    def test_repeated_calls_are_idempotent(self):
        self._write(self.old_path, "veri")
        first = migrate_legacy_path(self.old_path, self.new_path)
        second = migrate_legacy_path(self.old_path, self.new_path)
        self.assertTrue(first)
        self.assertFalse(second)


if __name__ == "__main__":
    unittest.main()
