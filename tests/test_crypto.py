import sys
import os
import unittest
from unittest import mock


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.crypto import DEFAULT_PASSWORD, encrypt, decrypt
from utils.errors import (
    DecryptionError,
    EncryptionError,
    IntegrityVerificationError,
)

class CryptoCompatibilityTest(unittest.TestCase):
    def test_current_cipher_round_trip(self):
        """It now exercises the NEW (AEAD) scheme by default -- not CBC as before. The
        old scheme's round trip is verified in a separate test
        (LegacyFormatBackwardCompatibilityTest) against a real old blob.
        """
        value = "Helysofer güvenli veri"
        self.assertEqual(decrypt(encrypt(value)), value)

    def test_new_ciphertext_is_marked_with_the_aead_prefix(self):
        token = encrypt("herhangi bir veri")
        self.assertTrue(token.startswith("AEADv1:"))


class LegacyFormatBackwardCompatibilityTest(unittest.TestCase):
    """The real point of the AEAD move: `encrypt()` NEVER
    PRODUCES the old AES-CBC format any more, but existing old data must stay
    readable FOREVER -- with no migration and no loss of user data.

    The blob below is A CLEAN PRODUCTION: it was produced by really running
    this module in its state BEFORE the move to AEAD
    (`encrypt("Market Alışverişi - 150,50 TL", DEFAULT_PASSWORD)`) -- it was NOT
    reconstructed from an assumption or by using this file's NEW code. That is
    what lets the test really verify "is the old format still readable"; it is
    not a circular, self-verifying test.
    """

    _REAL_LEGACY_BLOB = (
        "jv0+2I14CybLEXqpyXgmlTsjBp4lzc2RvRdFvElllXp112r2xpjPBBMAenlFJba"
        "FtQMj0ojOQ9L1Byg2+tBv5g=="
    )
    _REAL_LEGACY_PLAINTEXT = "Market Alışverişi - 150,50 TL"

    def test_pre_existing_legacy_ciphertext_still_decrypts_correctly(self):
        result = decrypt(self._REAL_LEGACY_BLOB, DEFAULT_PASSWORD)
        self.assertEqual(result, self._REAL_LEGACY_PLAINTEXT)

    def test_legacy_ciphertext_has_no_aead_prefix(self):
        """The reason the format distinction is SAFE: the base64 alphabet never
        contains `:`, so no real old ciphertext can accidentally begin with
        `AEADv1:`.
        """
        self.assertFalse(self._REAL_LEGACY_BLOB.startswith("AEADv1:"))


class FailClosedHandlingTest(unittest.TestCase):
    """Compatibility dispatcher never converts failures into usable data."""

    def test_corrupted_legacy_ciphertext_raises(self):
        with self.assertRaises(DecryptionError):
            decrypt("bu-gecerli-bir-base64-degil-!!!")

    def test_truncated_ciphertext_still_falls_back_gracefully(self):
        """A payload shorter than 16 bytes (with no IV) can be valid base64 but gives
        AES.new an invalid IV -- a ValueError, which must still be caught (the
        old path, with no AEADv1: prefix).
        """
        import base64
        short_payload = base64.b64encode(b"kisa").decode("utf-8")
        with self.assertRaises(DecryptionError):
            decrypt(short_payload)

    def test_corrupted_new_format_ciphertext_raises_integrity_error(self):
        token = encrypt("hassas veri")
        tampered = token[:-4] + "XXXX"
        with self.assertRaises(IntegrityVerificationError):
            decrypt(tampered)

    def test_unrelated_bug_inside_legacy_decrypt_still_propagates(self):
        """A bug unrelated to decryption INSIDE the old CBC path (a programming error
        simulated here, say) must not be hidden behind '[Şifreli Veri]' and
        swallowed silently. Because `unpad` is called only inside
        `_decrypt_legacy_cbc`, it is exercised against a genuinely old-format
        input -- the new format never visits that function.
        """
        with mock.patch(
            "utils.crypto.unpad", side_effect=RuntimeError("beklenmedik bug")
        ):
            with self.assertRaises(RuntimeError):
                decrypt(
                    LegacyFormatBackwardCompatibilityTest._REAL_LEGACY_BLOB,
                    DEFAULT_PASSWORD,
                )

    def test_unrelated_bug_inside_aead_decrypt_still_propagates(self):
        """The same invariant, for the NEW (AEAD) path."""
        token = encrypt("test verisi")
        with mock.patch(
            "utils.crypto.aead_crypto.decrypt",
            side_effect=RuntimeError("beklenmedik bug"),
        ):
            with self.assertRaises(RuntimeError):
                decrypt(token)

    def test_unrelated_bug_inside_encrypt_now_propagates(self):
        with mock.patch(
            "utils.crypto.aead_crypto.encrypt",
            side_effect=RuntimeError("beklenmedik bug"),
        ):
            with self.assertRaises(RuntimeError):
                encrypt("test verisi")

    def test_encrypt_failure_never_returns_plaintext(self):
        with mock.patch(
            "utils.crypto._get_aead_key", return_value=b"cok-kisa"
        ):
            with self.assertRaises(EncryptionError):
                encrypt("hassas veri")


class AeadKeyLazyResolutionTest(unittest.TestCase):
    """The same principle as utils/app_paths.py's own: merely importing
    `utils.crypto` (or even calling encrypt/decrypt for empty/None data) MUST
    NOT CREATE a real key file. Dozens of test files import this module
    indirectly; if the import itself produced a side effect, every test run
    would touch the developer's real home directory (run_tests.py's
    XDG_DATA_HOME sandbox is a second guarantee of this, not the first -- the
    first is this behaviour itself).
    """

    def test_empty_and_none_values_never_touch_the_key_provider(self):
        with mock.patch("utils.crypto._get_aead_key") as get_key:
            self.assertIsNone(encrypt(None))
            self.assertEqual(encrypt(""), "")
            self.assertIsNone(decrypt(None))
            self.assertEqual(decrypt(""), "")
        get_key.assert_not_called()


if __name__ == "__main__":
    unittest.main()
