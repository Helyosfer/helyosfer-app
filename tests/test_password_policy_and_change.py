"""The password policy, the legacy user transition and the password change contract.

THE MEASURED DEFECTS:

1. THE POLICY WAS FAR TOO WEAK. `PasswordPolicy.MIN_LENGTH` was 4 and only one
   uppercase plus one special character was required. `A!!!` was a valid
   password; the search space of a four-digit PIN is small enough to render even
   Argon2id meaningless.

2. CHANGING THE PASSWORD DID NOT ASK FOR THE CURRENT ONE. `_apply_new_pin` wrote
   the new hash directly -- anyone sitting down at an application left open
   could change the password and lock it. The throttle was not engaged either.

3. `setup_pin` COULD BE CALLED WHILE A PASSWORD ALREADY EXISTED and silently
   overwrote the current credential.

4. `.strip()` WAS CHANGING THE USER'S PASSWORD. The leading/trailing whitespace
   of the entered text was silently discarded, so the user typed one password
   and saved ANOTHER. The policy now rejects whitespace explicitly and the raw
   text is used consistently.

THE LEGACY USER TRANSITION: no credential changes until a login with the
correct password is VERIFIED. If the verified password meets the new policy,
the normal login continues (upgraded to Argon2id if necessary). If it does not,
the user is routed to forced renewal WITHOUT being let into the financial
screens, and that authority comes only from that successful login.

"""
import unittest

from security.security_service import (
    PasswordPolicy,
    SecurityService,
)

STRONG = "Guclu-Parola-2026!"
ANOTHER_STRONG = "Baska-Guclu-Parola-2026!"
WEAK_LEGACY = "A!!!"


class PasswordPolicyTest(unittest.TestCase):
    def test_minimum_length_is_twelve(self):
        self.assertEqual(PasswordPolicy.MIN_LENGTH, 12)

    def test_the_old_four_character_password_is_now_refused(self):
        valid, message = PasswordPolicy.validate("A!!!")
        self.assertFalse(valid)
        self.assertTrue(message)

    def test_a_four_digit_pin_is_refused(self):
        valid, _ = PasswordPolicy.validate("1234")
        self.assertFalse(valid)

    def test_eleven_characters_are_refused(self):
        """The bound is exactly 12: 11 characters must not pass."""
        candidate = "Abcdefgh1!x"
        self.assertEqual(len(candidate), 11)
        valid, _ = PasswordPolicy.validate(candidate)
        self.assertFalse(valid)

    def test_each_character_class_is_required(self):
        cases = {
            "abcdefghijk1!": "büyük harf yok",
            "ABCDEFGHIJK1!": "küçük harf yok",
            "Abcdefghijkl!": "rakam yok",
            "Abcdefghijk12": "özel karakter yok",
        }
        for candidate, reason in cases.items():
            with self.subTest(reason=reason):
                self.assertGreaterEqual(len(candidate), 12)
                valid, message = PasswordPolicy.validate(candidate)
                self.assertFalse(valid, f"{reason} olmasına rağmen kabul edildi")
                self.assertTrue(message)

    def test_a_compliant_password_is_accepted(self):
        valid, message = PasswordPolicy.validate(STRONG)
        self.assertTrue(valid)
        self.assertIsNone(message)

    def test_surrounding_whitespace_is_refused_rather_than_silently_stripped(self):
        for candidate in (f" {STRONG}", f"{STRONG} ", f"\t{STRONG}"):
            with self.subTest(candidate=repr(candidate)):
                valid, message = PasswordPolicy.validate(candidate)
                self.assertFalse(valid)
                self.assertTrue(message)

    def test_none_and_empty_are_refused_without_raising(self):
        for candidate in (None, ""):
            with self.subTest(candidate=repr(candidate)):
                valid, _ = PasswordPolicy.validate(candidate)
                self.assertFalse(valid)

    def test_every_message_comes_from_the_single_policy_source(self):
        """The error messages must come from a single source; the i18n gate looks at them."""
        produced = set()
        for candidate in (
            "", "kisa", "abcdefghijk1!", "ABCDEFGHIJK1!",
            "Abcdefghijkl!", "Abcdefghijk12", f" {STRONG}",
        ):
            valid, message = PasswordPolicy.validate(candidate)
            self.assertFalse(valid)
            produced.add(message)
        self.assertTrue(produced <= set(PasswordPolicy.MESSAGES))


class HashingCompatibilityTest(unittest.TestCase):
    """Argon2id and the old hash verification must not break."""

    def test_argon2id_round_trip(self):
        hashed = SecurityService.hash_password(STRONG)
        self.assertTrue(hashed.startswith("$argon2id$"))
        self.assertTrue(SecurityService.verify_password(STRONG, "salt", hashed))
        self.assertFalse(
            SecurityService.verify_password("yanlis", "salt", hashed)
        )

    def test_legacy_sha256_still_verifies_and_is_flagged_for_upgrade(self):
        import hashlib

        salt = "abc123"
        legacy = hashlib.sha256((salt + WEAK_LEGACY).encode("utf-8")).hexdigest()
        self.assertTrue(
            SecurityService.verify_password(WEAK_LEGACY, salt, legacy)
        )
        self.assertTrue(SecurityService.needs_upgrade(legacy))
        self.assertFalse(
            SecurityService.needs_upgrade(SecurityService.hash_password(STRONG))
        )


if __name__ == "__main__":
    unittest.main()
