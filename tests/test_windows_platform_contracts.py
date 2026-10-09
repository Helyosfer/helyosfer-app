"""Platform contracts that must really run on Windows.

THE PURPOSE OF THIS FILE is to turn the claim "tested on Windows" from a mock
into a MEASUREMENT. There are two separate test classes and the split is
deliberate:

  * Ones running INDEPENDENTLY of the platform -- the logic is the same
    everywhere, but the cost of it breaking is paid on Windows (a non-ASCII
    profile path, a long path, a file lock, the DPAPI race branch). These also
    run on a development machine, so a regression is caught without waiting for
    Windows CI.

  * Ones running ONLY on Windows (`skipUnless(os.name == "nt")`) -- a real
    `CryptProtectData`/`CryptUnprotectData` call. This path had NEVER RUN
    ANYWHERE until now: the DPAPI tests in `tests/test_key_provider.py` inject a
    fake protector, so what they verify is the wrapper logic, not the Windows
    API itself. The application uses the real path when it opens on Windows, but
    the startup smoke test may trigger no encryption/decryption at all on an
    empty profile -- so there was no deterministic evidence.

WHAT IS NOT HERE BECAUSE IT NEEDS A REAL MACHINE (a separate round):
SmartScreen/Defender reputation, DPAPI failing to decrypt for ANOTHER Windows
user, persistence after a restart, real DPI scaling, IME/keyboard behaviour,
installation with a non-admin user. None of these count as "passed" here.

"""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from utils.key_provider import DpapiKeyProvider, FileKeyProvider


NON_ASCII_PROFILE = "Çağrı Şıkğüöİ"


class _FakeProtector:
    """Imitates DPAPI's shape: a protected blob IS NOT the raw key."""

    def protect(self, data):
        return b"protected:" + data[::-1]

    def unprotect(self, data):
        if not data.startswith(b"protected:"):
            raise OSError("tampered")
        return data[len(b"protected:"):][::-1]


class KeyCreationRaceContract(unittest.TestCase):
    """The LOSER of the key-creation race must get the key on disk.

    `FileKeyProvider` resolves this through the `os.link` ordering and its own
    documentation describes it as "silent key destruction": if the loser
    carries on with their own key, everything encrypted with that key becomes
    permanently unreadable once the process closes.

    The race is not theoretical. `utils/key_provider.py`'s own note says: "at
    startup the crypto warm-up thread and the data thread can trigger the first
    decryption at the same time". On Windows the provider for that path is
    `DpapiKeyProvider`.
    """

    def _losing_creation(self, provider_factory):
        """`_create_atomically` while the file ALREADY exists -- the losing branch of the race.

        This is exactly the state seen by a second writer intervening between
        `get_or_create_key`'s `load_key()` check and `os.link`.
        """
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "encryption.key")
            winner = provider_factory(path).get_or_create_key()
            loser = provider_factory(path)
            returned = loser._create_atomically(os.urandom(32))
            return winner, returned, loser.load_key()

    def test_file_provider_loser_returns_the_stored_key(self):
        winner, returned, on_disk = self._losing_creation(FileKeyProvider)
        self.assertEqual(returned, winner)
        self.assertEqual(on_disk, winner)

    def test_dpapi_provider_loser_returns_the_stored_key(self):
        winner, returned, on_disk = self._losing_creation(
            lambda path: DpapiKeyProvider(path, protector=_FakeProtector()))
        self.assertEqual(
            returned, winner,
            "yarışı kaybeden, diske hiç yazılmamış kendi anahtarını döndürdü — "
            "onunla şifrelenen veri kalıcı olarak okunamaz olur",
        )
        self.assertEqual(on_disk, winner)

    def test_dpapi_provider_winner_still_returns_its_own_key(self):
        """The fix resolving the race must not break the normal path."""
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "encryption.key")
            provider = DpapiKeyProvider(path, protector=_FakeProtector())
            created = provider.get_or_create_key()
            self.assertEqual(provider.load_key(), created)
            self.assertEqual(
                DpapiKeyProvider(path, protector=_FakeProtector()).load_key(),
                created)


class NonAsciiAndLongProfilePaths(unittest.TestCase):
    """The round must complete when the profile path is non-ASCII or very long.

    `HELYOSFER_HOME` is an override that also exists in production
    (utils/app_paths.py); not a gate invented by the test. The whole chain is
    measured: path resolution -> the SQLite file -> the key file -> the
    encrypted write -> the read.
    """

    def _round_trip(self, root):
        """Opens an account at the given root and reads the encrypted amount back."""
        with mock.patch.dict(os.environ, {"HELYOSFER_HOME": str(root)}):
            from utils.app_paths import data_dir

            resolved = Path(data_dir())
            os.makedirs(resolved, exist_ok=True)
            db_path = resolved / "finance.db"
            key_path = resolved / "encryption.key"
            key = FileKeyProvider(str(key_path)).get_or_create_key()

            with mock.patch("database.db.DB_NAME", str(db_path)), \
                    mock.patch("utils.crypto._get_aead_key", return_value=key):
                from database.init_db import initialize_database
                from services.account_service import AccountService
                from services.transaction_service import TransactionService

                initialize_database()
                account_id = AccountService.create_account(
                    "Türkçe Hesap", "checking", initial_balance=1000.0)
                TransactionService.add_transaction(
                    account_id, 249.99, "expense", "Market", "Şırınga & çilek",
                    detect_subscription=False)
                balance = AccountService.get_account(account_id)["balance"]
                rows = TransactionService.get_recent_for_account(
                    account_id, limit=None)
        return db_path, key_path, balance, rows

    def test_non_ascii_profile_directory_round_trips(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / NON_ASCII_PROFILE / "Helyosfer"
            db_path, key_path, balance, rows = self._round_trip(root)

            self.assertTrue(db_path.is_file(), "veritabanı ASCII dışı yolda açılmadı")
            self.assertTrue(key_path.is_file(), "anahtar ASCII dışı yolda yazılmadı")
            self.assertAlmostEqual(balance, 1000.0 - 249.99, places=2)
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(rows[0]["amount"], 249.99, places=2)


            self.assertEqual(rows[0]["description"], "Şırınga & çilek")

    def test_deep_profile_directory_round_trips(self):
        """The 260-character limit on Windows -- a long but realistic profile path.

        We are not aiming to EXCEED the limit (that would make the test itself
        environment-dependent); we pin that a path APPROACHING the limit
        works.
        """
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)

            for _ in range(4):
                root = root / ("u" * 40)
            db_path, _key, balance, rows = self._round_trip(root / "Helyosfer")
            self.assertTrue(db_path.is_file())
            self.assertAlmostEqual(balance, 1000.0 - 249.99, places=2)
            self.assertEqual(len(rows), 1)


class BackupSurvivesAnOpenDatabase(unittest.TestCase):
    """Backup/restore must work AFTER the database has been used.

    On Windows an open handle drops `os.replace`/`os.rename` with a
    `PermissionError` -- it does not on Linux.
    `database/init_db.py::initialize_database` takes closing the connection on
    every exit path seriously for exactly this reason ("on Windows it means a
    lock held on finance.db, blocking the next restore/rename/delete step").
    That rationale was only a comment until now; it is measured here.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="helyosfer-winlock-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "finance.db"
        self.key_path = self.root / "encryption.key"
        self.key = os.urandom(32)
        self.key_path.write_bytes(self.key)

        self._db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self._key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key)
        self._db_patch.start()
        self._key_patch.start()
        self.addCleanup(self._db_patch.stop)
        self.addCleanup(self._key_patch.stop)

        from database.init_db import initialize_database
        initialize_database()

    def test_backup_and_restore_after_real_database_use(self):
        from services.account_service import AccountService
        from services.backup_service import create_backup, restore_backup
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account(
            "Kilit", "checking", initial_balance=5000.0)
        TransactionService.add_transaction(
            account_id, 100.0, "expense", "Market", "x",
            detect_subscription=False)

        package = self.root / "yedek.helyosfer-backup"
        create_backup(package, "cok-guclu-yedek-parolasi-2026", db_path=self.db_path,
                      key_path=self.key_path)
        self.assertTrue(package.is_file())


        TransactionService.add_transaction(
            account_id, 250.0, "expense", "Market", "y",
            detect_subscription=False)
        self.assertAlmostEqual(
            AccountService.get_account(account_id)["balance"], 4650.0, places=2)

        restore_backup(package, "cok-guclu-yedek-parolasi-2026", db_path=self.db_path,
                       key_path=self.key_path)


        self.assertAlmostEqual(
            AccountService.get_account(account_id)["balance"], 4900.0, places=2)


        with closing(sqlite3.connect(self.db_path)) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(count, 1)


@unittest.skipUnless(os.name == "nt", "gerçek DPAPI yalnız Windows'ta var")
class RealWindowsDpapi(unittest.TestCase):
    """REAL `CryptProtectData`/`CryptUnprotectData` -- NO fake protector.

    This class runs only on the Windows runner; it is skipped on Linux, and a
    skipped test PROVES NOTHING. Its scope is limited too: the same user, the
    same session. That the key CANNOT be decrypted by ANOTHER Windows user and
    CAN be opened after a restart is to be verified on a real machine, NOT
    here.
    """

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="helyosfer-dpapi-")
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "encryption.key.dpapi")


    CRYPTPROTECT_LOCAL_MACHINE = 0x4

    def test_key_is_never_protected_with_machine_scope(self):
        """Pins the MECHANISM of cross-user isolation.

        An end-to-end run with a second Windows account could not be done on
        this machine (only one active regular account exists). What can be
        done, and is actually more durable, is this: measuring BEHAVIOURALLY
        that the flag is never given. Searching the source text was not
        enough -- here the real `CryptProtectData` call is intercepted and
        `dwFlags` captured.

        WHAT IT PROVES: by its own contract, Windows binds the blob to the
        calling user account; another user cannot decrypt it.
        WHAT IT DOES NOT PROVE: that Windows follows its own contract (we trust
        the operating system) or that it was run with a real second account.

        Its real value is against regression: if someone adds this flag one
        day so "the machine's service can read it too", this test turns red
        instead of silently opening to every user.
        """
        import ctypes
        from unittest import mock as _mock
        from utils.key_provider import _WindowsDpapi

        real = ctypes.windll.crypt32.CryptProtectData
        captured = {}

        def _spy(*args):


            captured["flags"] = args[5]
            return real(*args)

        with _mock.patch.object(
            ctypes.windll.crypt32, "CryptProtectData", _spy
        ):
            _WindowsDpapi().protect(os.urandom(32))

        self.assertIn(
            "flags", captured,
            "CryptProtectData hiç çağrılmadı — test bir şey ölçmedi",
        )
        self.assertEqual(
            captured["flags"] & self.CRYPTPROTECT_LOCAL_MACHINE, 0,
            "anahtar MAKİNE kapsamıyla korunuyor: makinedeki her Windows "
            "kullanıcısı çözebilir",
        )

    def test_unprotect_also_stays_in_user_scope(self):
        """The unprotect side must be flag-free too; an asymmetry is a silent surprise."""
        import ctypes
        from unittest import mock as _mock
        from utils.key_provider import _WindowsDpapi

        dpapi = _WindowsDpapi()
        blob = dpapi.protect(os.urandom(32))
        real = ctypes.windll.crypt32.CryptUnprotectData
        captured = {}

        def _spy(*args):
            captured["flags"] = args[5]
            return real(*args)

        with _mock.patch.object(
            ctypes.windll.crypt32, "CryptUnprotectData", _spy
        ):
            dpapi.unprotect(blob)

        self.assertIn("flags", captured)
        self.assertEqual(
            captured["flags"] & self.CRYPTPROTECT_LOCAL_MACHINE, 0
        )

    def test_protect_unprotect_round_trip(self):
        from utils.key_provider import _WindowsDpapi

        dpapi = _WindowsDpapi()
        secret = os.urandom(32)
        blob = dpapi.protect(secret)
        self.assertNotEqual(blob, secret, "korunmuş blob ham anahtarı taşıyor")
        self.assertNotIn(secret, blob, "ham anahtar blob'un içinde düz duruyor")
        self.assertEqual(dpapi.unprotect(blob), secret)

    def test_tampered_blob_is_rejected(self):
        from utils.key_provider import _WindowsDpapi

        dpapi = _WindowsDpapi()
        blob = bytearray(dpapi.protect(os.urandom(32)))
        blob[-1] ^= 0xFF
        with self.assertRaises(OSError):
            dpapi.unprotect(bytes(blob))

    def test_key_survives_a_new_provider_instance(self):
        """The in-test equivalent of a process restart."""
        created = DpapiKeyProvider(self.path).get_or_create_key()
        self.assertEqual(len(created), 32)
        self.assertEqual(DpapiKeyProvider(self.path).get_or_create_key(),
                         created)

    def test_stored_file_never_contains_the_raw_key(self):
        created = DpapiKeyProvider(self.path).get_or_create_key()
        with open(self.path, "rb") as stream:
            stored = stream.read()
        self.assertNotEqual(stored, created)
        self.assertNotIn(created, stored)

    def test_platform_factory_selects_dpapi_and_reports_it_as_secure(self):
        from utils.key_provider import create_platform_key_provider

        provider = create_platform_key_provider(self.temp.name)
        self.assertEqual(provider.status.method, "Windows DPAPI")
        self.assertTrue(provider.status.secure_store)
        self.assertIsNone(provider.status.warning)


        key = provider.get_or_create_key()
        self.assertEqual(len(key), 32)
        self.assertEqual(
            create_platform_key_provider(self.temp.name).get_or_create_key(),
            key)


if __name__ == "__main__":
    unittest.main()
