"""`FileKeyProvider` -- verifies how a key is
persistently written to and read from a given path, without deciding WHERE it
should be written (that is `utils/app_paths.py`'s job).
"""
import os
import stat
import tempfile
import threading
import unittest
from unittest import mock

from utils.errors import KeyUnavailableError
from utils.key_provider import (
    DpapiKeyProvider,
    FileKeyProvider,
    KeyringKeyProvider,
    MigratingKeyProvider,
    KeyProtectionStatus,
    create_platform_key_provider,
)


class FileKeyProviderTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.key_path = os.path.join(self.tmpdir, "secret.key")

    def tearDown(self):
        for root, dirs, files in os.walk(self.tmpdir, topdown=False):
            for name in files:
                os.chmod(os.path.join(root, name), 0o700)
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(self.tmpdir)

    def test_first_call_creates_a_32_byte_key(self):
        provider = FileKeyProvider(self.key_path)
        key = provider.get_or_create_key()
        self.assertEqual(len(key), 32)
        self.assertTrue(os.path.exists(self.key_path))

    def test_second_call_returns_the_same_key(self):
        provider = FileKeyProvider(self.key_path)
        first = provider.get_or_create_key()
        second = provider.get_or_create_key()
        self.assertEqual(first, second)

    def test_a_fresh_provider_instance_reads_the_persisted_key(self):
        """The real test of persistence: is the file itself being kept rather than
        in-memory state -- a new provider object must be able to read the same
        key.
        """
        first_key = FileKeyProvider(self.key_path).get_or_create_key()
        second_key = FileKeyProvider(self.key_path).get_or_create_key()
        self.assertEqual(first_key, second_key)

    def test_different_key_paths_get_different_random_keys(self):
        key_a = FileKeyProvider(self.key_path).get_or_create_key()
        key_b = FileKeyProvider(
            os.path.join(self.tmpdir, "other.key")
        ).get_or_create_key()
        self.assertNotEqual(key_a, key_b)

    def test_creates_missing_parent_directories(self):
        nested_path = os.path.join(self.tmpdir, "a", "b", "c", "secret.key")
        provider = FileKeyProvider(nested_path)
        key = provider.get_or_create_key()
        self.assertEqual(len(key), 32)

    def test_corrupted_key_file_raises(self):
        with open(self.key_path, "wb") as f:
            f.write(b"too-short")
        provider = FileKeyProvider(self.key_path)
        with self.assertRaises(KeyUnavailableError):
            provider.get_or_create_key()

    def test_concurrent_first_creation_yields_one_shared_key(self):
        """The application has no process-level single-instance protection, so on a
        fresh installation double-clicking the shortcut puts two processes into
        generating a key at the same time -- ordinary user behaviour, not an
        attack.

        This test locks down two separate bugs at once:
          1) `exists()` + write only: the two processes generate DIFFERENT keys
             and the second overwrites the first; everything the first
             encrypted becomes PERMANENTLY unrecoverable.
          2) `O_EXCL` only: the file is briefly visible as EMPTY between
             creation and the content being written; the loser of the race
             reads in that window and blows up with "Key file is corrupt: 0
             bytes". (This was observed empirically in a real 16-process run --
             it is not theoretical.)
        The correct behaviour: every process returns THE SAME, COMPLETE key.
        """
        import concurrent.futures

        barrier = threading.Barrier(8)

        def create():
            barrier.wait()
            return FileKeyProvider(self.key_path).get_or_create_key()

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            keys = [f.result() for f in
                    [pool.submit(create) for _ in range(8)]]

        with open(self.key_path, "rb") as f:
            on_disk = f.read()

        self.assertEqual(len(set(keys)), 1, "süreçler farklı anahtar üretti")
        self.assertEqual(len(on_disk), 32)
        self.assertTrue(all(k == on_disk for k in keys),
                        "dönen anahtar diskteki anahtarla aynı değil")

    def test_no_temp_files_are_left_behind(self):
        """The atomic link goes through a temporary file; that file must be cleaned
        up in every case and must not be left behind in the key directory.
        """
        FileKeyProvider(self.key_path).get_or_create_key()
        leftovers = [n for n in os.listdir(self.tmpdir) if ".tmp." in n]
        self.assertEqual(leftovers, [])

    @unittest.skipIf(
        os.name == "nt",
        "POSIX mod bitleri Windows'ta anlam taşımıyor — aşağıdaki Windows "
        "testine bakın.",
    )
    def test_key_file_is_owner_only_readable(self):
        provider = FileKeyProvider(self.key_path)
        provider.get_or_create_key()
        mode = stat.S_IMODE(os.stat(self.key_path).st_mode)
        self.assertEqual(mode, 0o600)

    @unittest.skipUnless(os.name == "nt", "yalnızca Windows davranışı")
    def test_key_file_exists_on_windows_where_chmod_cannot_express_0600(self):
        """On Windows, `chmod(0o600)` DOES NOT PRODUCE the intended restriction.

        Measured (Windows CI): `os.stat().st_mode` returns 0o666, not 0o600.
        Windows does not apply POSIX permission bits as a real access control;
        the protection comes from ACLs. Leaving this test expecting 0o600 would
        be pretending to verify a guarantee that does not exist.

        On Windows the file key is a FALLBACK path anyway: the primary provider
        is DPAPI (utils/key_provider.py::WindowsDPAPIKeyProvider), which binds
        the key to the user account. The file also sits under the user profile,
        so its default ACL is already user-specific.

        What is verified here: the key file really is created and is a plain
        file. Real ACL verification requires pywin32 and is a separate job --
        `docs/KEY_MANAGEMENT.md` should state that limit explicitly.
        """
        provider = FileKeyProvider(self.key_path)
        provider.get_or_create_key()
        self.assertTrue(os.path.isfile(self.key_path))


class _FakeKeyringBackend:
    priority = 1


class _FakeKeyring:
    def __init__(self, available=True):
        self.backend = _FakeKeyringBackend()
        self.backend.priority = 1 if available else 0
        self.values = {}

    def get_keyring(self):
        return self.backend

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, value):
        self.values[(service, username)] = value


class _FakeProtector:
    def protect(self, data):
        return b"protected:" + data[::-1]

    def unprotect(self, data):
        if not data.startswith(b"protected:"):
            raise OSError("tampered")
        return data[len(b"protected:"):][::-1]


class PlatformKeyProviderTest(unittest.TestCase):
    def test_keyring_round_trip_survives_provider_restart(self):
        keyring = _FakeKeyring()
        first = KeyringKeyProvider(keyring_module=keyring)
        key = first.get_or_create_key()
        second = KeyringKeyProvider(keyring_module=keyring)
        self.assertEqual(second.get_or_create_key(), key)

    def test_unavailable_keyring_is_explicit(self):
        provider = KeyringKeyProvider(
            keyring_module=_FakeKeyring(available=False)
        )
        with self.assertRaises(KeyUnavailableError):
            provider.get_or_create_key()

    def test_dpapi_blob_never_contains_raw_key(self):
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "key.dpapi")
            key = DpapiKeyProvider(
                path, protector=_FakeProtector()
            ).get_or_create_key()
            with open(path, "rb") as stream:
                self.assertNotEqual(stream.read(), key)
            restarted = DpapiKeyProvider(path, protector=_FakeProtector())
            self.assertEqual(restarted.get_or_create_key(), key)

    def test_legacy_file_is_migrated_only_after_store_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            legacy_path = os.path.join(temp, "encryption.key")
            legacy = FileKeyProvider(legacy_path)
            key = legacy.get_or_create_key()
            primary = KeyringKeyProvider(keyring_module=_FakeKeyring())
            provider = MigratingKeyProvider(
                primary,
                legacy,
                KeyProtectionStatus("test store", True),
            )
            self.assertEqual(provider.get_or_create_key(), key)
            self.assertFalse(os.path.exists(legacy_path))
            self.assertFalse(os.path.exists(legacy_path + ".migrated"))
            self.assertEqual(primary.load_key(), key)

    def test_linux_factory_reports_insecure_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch("utils.key_provider.sys.platform", "linux"):
                provider = create_platform_key_provider(
                    temp, keyring_module=_FakeKeyring(available=False)
                )
            self.assertFalse(provider.status.secure_store)
            self.assertIsNotNone(provider.status.warning)


if __name__ == "__main__":
    unittest.main()
