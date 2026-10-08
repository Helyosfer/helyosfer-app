"""The password length contract must come from a SINGLE source.

THE MEASURED INCONSISTENCY:

    the password change dialog           : max length = 64
    the setup and login fields           : max length = 32
    PasswordPolicy                       : NO UPPER BOUND

    PasswordPolicy.validate("Ab1!" + "x" * 61)  ->  (True, None)   # 65 characters
    PasswordPolicy.validate("Ab1!" + "x" * 196) ->  (True, None)   # 200 characters

The field limit DID NOT TRUNCATE the text; it only put the field into an
error state. So this was not an account lock; but the policy said
"valid" while the interface could show red, and two different numbers lived on
two different screens. The contract was reduced to a single number:
`PasswordPolicy.MAX_LENGTH`.

AN OLD LONG PASSWORD: an account set up with a password longer than 64 must not
be refused and locked out WITHOUT verification. It is first verified against
the existing hash; if it is correct the user goes to forced renewal without
being let into the financial screens.

"""
import unittest
from pathlib import Path

from security.security_service import PasswordPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: A policy-compliant, 64-character password.
AT_LIMIT = "Ab1!" + "x" * 60
#: A 65-character password, one character too long.
OVER_LIMIT = "Ab1!" + "x" * 61


class PasswordLengthPolicyTest(unittest.TestCase):
    def test_the_limit_is_declared_once(self):
        self.assertEqual(PasswordPolicy.MAX_LENGTH, 64)
        self.assertGreater(PasswordPolicy.MAX_LENGTH, PasswordPolicy.MIN_LENGTH)

    def test_exactly_the_limit_is_accepted(self):
        self.assertEqual(len(AT_LIMIT), PasswordPolicy.MAX_LENGTH)
        valid, message = PasswordPolicy.validate(AT_LIMIT)
        self.assertTrue(valid, message)
        self.assertIsNone(message)

    def test_one_character_over_the_limit_is_refused(self):
        self.assertEqual(len(OVER_LIMIT), PasswordPolicy.MAX_LENGTH + 1)
        valid, message = PasswordPolicy.validate(OVER_LIMIT)
        self.assertFalse(valid)
        self.assertEqual(message, PasswordPolicy.TOO_LONG)

    def test_a_very_long_password_is_refused_too(self):
        valid, message = PasswordPolicy.validate("Ab1!" + "x" * 5000)
        self.assertFalse(valid)
        self.assertEqual(message, PasswordPolicy.TOO_LONG)

    def test_the_message_lives_in_the_single_policy_source(self):
        self.assertIn(PasswordPolicy.TOO_LONG, PasswordPolicy.MESSAGES)

    def test_the_message_has_an_english_translation(self):
        from ui.i18n import tr

        for message in PasswordPolicy.MESSAGES + (PasswordPolicy.REQUIREMENTS,):
            with self.subTest(message=message):
                self.assertNotEqual(tr(message, "en"), message)

    def test_the_requirements_text_states_both_bounds(self):
        self.assertIn(str(PasswordPolicy.MIN_LENGTH), PasswordPolicy.REQUIREMENTS)
        self.assertIn(str(PasswordPolicy.MAX_LENGTH), PasswordPolicy.REQUIREMENTS)






class _Store:
    def __init__(self):
        self.data = {}
        self.writes = []

    def exists(self, key):
        return key in self.data

    def get(self, key):
        return dict(self.data[key])

    def put(self, key, **values):
        self.data[key] = dict(values)
        self.writes.append((key, dict(values)))


class _Field:
    def __init__(self, text=""):
        self.text = text


class _Ids(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


class _ScreenManager:
    def __init__(self):
        self.current = "login"


class _Root:
    def __init__(self, ids):
        self.ids = ids


if __name__ == "__main__":
    unittest.main()
