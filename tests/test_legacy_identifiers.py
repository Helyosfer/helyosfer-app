"""The two identifiers from before the rename must stay BYTE FOR BYTE the same.

WHY IT EXISTS: the application's name before Helyosfer is stored base64-encoded
in `utils/app_paths.py` so it does not appear as plain text in the code base.
This is NOT a security measure -- it is name hygiene. But an encoded constant
being corrupted by accident is far more silent than a plain-text one: nobody
can look at the string `Zmlub3Jh` and say "that is wrong".

So the expected values are written out explicitly HERE. Changing either is
FORBIDDEN, and for different reasons:

  * `LEGACY_CBC_PASSWORD` -- the ONLY decryption key for records encrypted with
    the legacy AES-256-CBC scheme. If it changes, the amounts and descriptions in
    old profiles become permanently unreadable. There is no way back.

  * `LEGACY_CONFIG_FILENAME` -- the name of the old settings file sitting on
    disk. If it changes, that file cannot be found and the user's settings do
    not migrate; it does not even error, it just disappears silently.

This test decodes the encoding and compares it against the expectation. If the
encoded line changes, this breaks -- that is the safety net being built.

"""

import base64
import unittest

from utils.app_paths import LEGACY_CBC_PASSWORD, LEGACY_CONFIG_FILENAME


_EXPECTED_CBC_PASSWORD = base64.b64decode("Zmlub3JhX3NlY3VyZV8yMDI2").decode("ascii")
_EXPECTED_CONFIG_FILENAME = base64.b64decode("Zmlub3JhX2NvbmZpZy5qc29u").decode("ascii")


class LegacyIdentifiersAreFrozen(unittest.TestCase):

    def test_cbc_password_is_unchanged(self):
        """The decryption key for old records -- if it changes, the data becomes unreadable."""
        self.assertEqual(LEGACY_CBC_PASSWORD, _EXPECTED_CBC_PASSWORD)

    def test_config_filename_is_unchanged(self):
        """The name of the old settings file to be migrated -- if it changes, the migration silently misses it."""
        self.assertEqual(LEGACY_CONFIG_FILENAME, _EXPECTED_CONFIG_FILENAME)

    def test_database_secret_key_still_resolves_to_the_legacy_password(self):
        """`database.db.SECRET_KEY` must carry the same value.

        Hundreds of call sites use this name; the value shifting while binding
        to the shared constant would break every path that reads old data at
        once.
        """
        from database.db import SECRET_KEY

        self.assertEqual(SECRET_KEY, _EXPECTED_CBC_PASSWORD)

    def test_legacy_ciphertext_written_with_the_old_scheme_still_decrypts(self):
        """THE REAL GUARANTEE: a record written with the old scheme can still be decrypted.

        Comparing the constants is not enough -- the real question is whether
        that password actually opens the old format. The ciphertext is produced
        here, inside the test, with the old scheme itself (the same pattern as
        `tests/test_crypto_migration_service.py`); the production code is not
        extended for the test.
        """
        from Crypto.Cipher import AES
        from Crypto.Protocol.KDF import PBKDF2
        from Crypto.Util.Padding import pad

        from utils.crypto import STATIC_SALT, _decrypt_legacy_cbc

        iv = bytes(range(16))
        key = PBKDF2(LEGACY_CBC_PASSWORD, STATIC_SALT, dkLen=32, count=1_000_000)
        payload = iv + AES.new(key, AES.MODE_CBC, iv).encrypt(
            pad("1234.56".encode("utf-8"), 16))
        token = base64.b64encode(payload).decode("ascii")

        self.assertEqual(
            _decrypt_legacy_cbc(token, LEGACY_CBC_PASSWORD), "1234.56")


if __name__ == "__main__":
    unittest.main()
