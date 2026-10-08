import hashlib
import unittest

from security.security_service import SecurityService


class SecurityServiceTest(unittest.TestCase):
    def test_new_hash_is_argon2id_and_round_trips(self):
        pin_hash = SecurityService.hash_password("2468")
        self.assertTrue(pin_hash.startswith("$argon2id$"))
        self.assertTrue(SecurityService.verify_password("2468", None, pin_hash))

    def test_argon2id_hash_is_nondeterministic_but_both_verify(self):
        """Argon2id regenerates its own random salt on every call -- this is
        DELIBERATE (the same PIN always falling to the same hash is undesirable
        from a security standpoint). The raw hash strings must differ, and both
        must verify.
        """
        first = SecurityService.hash_password("2468")
        second = SecurityService.hash_password("2468")
        self.assertNotEqual(first, second)
        self.assertTrue(SecurityService.verify_password("2468", None, first))
        self.assertTrue(SecurityService.verify_password("2468", None, second))

    def test_wrong_pin_is_rejected(self):
        pin_hash = SecurityService.hash_password("2468")
        self.assertFalse(
            SecurityService.verify_password("1357", None, pin_hash)
        )

    def test_generated_salt_has_128_bits_of_hex_entropy(self):
        """generate_salt() is kept for backward compatibility (see the module
        docstring) -- new Argon2id hashes do not use it.
        """
        salt = SecurityService.generate_salt()
        self.assertEqual(len(salt), 32)
        int(salt, 16)

    def test_needs_upgrade_is_false_for_new_argon2id_hash(self):
        pin_hash = SecurityService.hash_password("2468")
        self.assertFalse(SecurityService.needs_upgrade(pin_hash))


class LegacySha256CompatibilityTest(unittest.TestCase):
    """Existing users' hash on disk is still in the old SHA-256 format. These
    must still verify correctly before they are migrated to Argon2id --
    otherwise everyone would be locked out as though they had forgotten their
    PIN.
    """

    def _legacy_hash(self, pin, salt):
        payload = (str(salt) + str(pin)).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def test_legacy_hash_still_verifies_correctly(self):
        salt = SecurityService.generate_salt()
        legacy_hash = self._legacy_hash("2468", salt)
        self.assertTrue(
            SecurityService.verify_password("2468", salt, legacy_hash)
        )

    def test_legacy_hash_rejects_wrong_pin(self):
        salt = SecurityService.generate_salt()
        legacy_hash = self._legacy_hash("2468", salt)
        self.assertFalse(
            SecurityService.verify_password("1357", salt, legacy_hash)
        )

    def test_needs_upgrade_is_true_for_legacy_hash(self):
        salt = SecurityService.generate_salt()
        legacy_hash = self._legacy_hash("2468", salt)
        self.assertTrue(SecurityService.needs_upgrade(legacy_hash))

    def test_lazy_migration_end_to_end(self):
        """The real scenario: verify with the old hash, and once needs_upgrade is
        seen, re-hash -- the result must now be Argon2id and must verify with
        both the old and the new PIN (the same PIN).
        """
        salt = SecurityService.generate_salt()
        legacy_hash = self._legacy_hash("2468", salt)

        self.assertTrue(
            SecurityService.verify_password("2468", salt, legacy_hash)
        )
        self.assertTrue(SecurityService.needs_upgrade(legacy_hash))

        upgraded_hash = SecurityService.hash_password("2468")

        self.assertFalse(SecurityService.needs_upgrade(upgraded_hash))
        self.assertTrue(
            SecurityService.verify_password("2468", None, upgraded_hash)
        )

    def test_malformed_hash_fails_closed_not_crashes(self):
        """A record in neither SHA-256 nor Argon2id format (a corrupted config) --
        no crash, stay on the safe side: the login is refused.
        """
        result = SecurityService.verify_password(
            "2468", "tuz", "ne-sha256-ne-argon2-olan-bir-string"
        )
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
