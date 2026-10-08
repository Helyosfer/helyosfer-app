"""Sign-in flows: setup, login, throttling, forced renewal and password change."""

import os
import tempfile
import unittest
from unittest import mock

from security.security_service import LoginThrottle, SecurityService
from services.auth_service import (
    ACCOUNT_SETUP, HOME, LOGIN, RENEWAL, SETUP, AuthService,
)
from utils.config_store import ConfigStore

STRONG = "Guclu-Parola-2026!"
OTHER = "Baska-Parola-2027?"


class AuthServiceTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = ConfigStore(os.path.join(self._tmp.name, "config.json"))
        self.auth = AuthService(self.store)
        self._route = mock.patch.object(
            AuthService, "screen_after_auth", return_value=HOME
        )
        self._route.start()
        self.addCleanup(self._route.stop)


class SetupTest(AuthServiceTestBase):
    def test_a_fresh_profile_starts_at_setup(self):
        self.assertEqual(self.auth.start_screen(), SETUP)

    def test_setup_stores_a_hash_and_never_the_password(self):
        result = self.auth.setup(STRONG, STRONG)
        self.assertTrue(result.ok)
        self.assertEqual(result.screen, HOME)
        record = self.store.get("security")
        self.assertTrue(record["is_set"])
        self.assertNotIn(STRONG, record["pin_hash"])
        self.assertEqual(self.auth.start_screen(), LOGIN)

    def test_a_weak_password_is_refused_with_the_policy_message(self):
        result = self.auth.setup("1234", "1234")
        self.assertFalse(result.ok)
        self.assertEqual(result.screen, SETUP)
        self.assertTrue(result.message)
        self.assertFalse(self.store.exists("security"))

    def test_a_mismatched_confirmation_is_refused(self):
        result = self.auth.setup(STRONG, OTHER)
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Passwords do not match.")

    def test_setup_cannot_overwrite_an_existing_credential(self):
        self.auth.setup(STRONG, STRONG)
        before = self.store.get("security")
        result = self.auth.setup(OTHER, OTHER)
        self.assertFalse(result.ok)
        self.assertEqual(result.screen, LOGIN)
        self.assertEqual(self.store.get("security"), before)


class LoginTest(AuthServiceTestBase):
    def setUp(self):
        super().setUp()
        self.auth.setup(STRONG, STRONG)

    def test_the_right_password_signs_in(self):
        result = self.auth.login(STRONG)
        self.assertTrue(result.ok)
        self.assertEqual(result.screen, HOME)

    def test_a_wrong_password_is_refused_and_counted(self):
        result = self.auth.login(OTHER)
        self.assertFalse(result.ok)
        self.assertEqual(result.message, "Incorrect password!")
        self.assertEqual(self.store.get("security_throttle")["failed_attempts"], 1)

    def test_repeated_failures_lock_even_the_right_password_out(self):
        for _ in range(LoginThrottle.FAILED_ATTEMPT_THRESHOLD):
            self.auth.login(OTHER)
        self.assertGreater(self.auth.seconds_locked(), 0)
        result = self.auth.login(STRONG)
        self.assertFalse(result.ok)
        self.assertTrue(result.message)
        self.assertNotEqual(result.message, "Incorrect password!")

    def test_a_successful_login_clears_the_counter(self):
        self.auth.login(OTHER)
        self.auth.login(STRONG)
        self.assertEqual(
            self.store.get("security_throttle"), LoginThrottle.record_success()
        )

    def test_login_without_a_credential_routes_to_setup(self):
        self.store.delete("security")
        self.assertEqual(self.auth.login(STRONG).screen, SETUP)

    def test_routing_sends_a_profile_without_accounts_to_onboarding(self):
        self._route.stop()
        try:
            with mock.patch(
                "services.account_service.AccountService.has_any_account",
                return_value=False,
            ):
                self.assertEqual(self.auth.screen_after_auth(), ACCOUNT_SETUP)
        finally:
            self._route.start()


class ForcedRenewalTest(AuthServiceTestBase):
    def _install(self, password):
        salt = SecurityService.generate_salt()
        self.store.put(
            "security", pin_hash=SecurityService.hash_password(password, salt),
            salt=salt, is_set=True,
        )

    def test_a_weak_existing_password_is_verified_then_sent_to_renewal(self):
        self._install("1234")
        result = self.auth.login("1234")
        self.assertTrue(result.ok)
        self.assertEqual(result.screen, RENEWAL)
        self.assertTrue(self.auth.renewal_required)

    def test_a_wrong_weak_password_does_not_reach_renewal(self):
        self._install("1234")
        self.assertFalse(self.auth.login("4321").ok)
        self.assertFalse(self.auth.renewal_required)

    def test_renewal_replaces_the_credential_and_returns_to_login(self):
        self._install("1234")
        self.auth.login("1234")
        result = self.auth.setup(STRONG, STRONG)
        self.assertTrue(result.ok)
        self.assertEqual(result.screen, LOGIN)
        self.assertFalse(self.auth.renewal_required)
        self.assertTrue(self.auth.login(STRONG).ok)
        self.assertFalse(self.auth.login("1234").ok)


class ChangePasswordTest(AuthServiceTestBase):
    def setUp(self):
        super().setUp()
        self.auth.setup(STRONG, STRONG)

    def test_change_requires_the_current_password(self):
        result = self.auth.change_password(OTHER, OTHER, OTHER)
        self.assertFalse(result.ok)
        self.assertTrue(self.auth.login(STRONG).ok)

    def test_a_valid_change_takes_effect(self):
        result = self.auth.change_password(STRONG, OTHER, OTHER)
        self.assertTrue(result.ok)
        self.assertEqual(result.screen, LOGIN)
        self.assertTrue(self.auth.login(OTHER).ok)
        self.assertFalse(self.auth.login(STRONG).ok)

    def test_the_new_password_must_differ_from_the_current_one(self):
        self.assertFalse(self.auth.change_password(STRONG, STRONG, STRONG).ok)

    def test_the_new_password_must_meet_the_policy(self):
        self.assertFalse(self.auth.change_password(STRONG, "1234", "1234").ok)


class ConfigStoreTest(unittest.TestCase):
    def test_values_survive_a_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "config.json")
            ConfigStore(path).put("display", style="Dark")
            self.assertEqual(ConfigStore(path).get("display"), {"style": "Dark"})

    def test_a_missing_record_reads_as_empty(self):
        with tempfile.TemporaryDirectory() as folder:
            store = ConfigStore(os.path.join(folder, "config.json"))
            self.assertEqual(store.get("nothing"), {})
            self.assertFalse(store.exists("nothing"))


if __name__ == "__main__":
    unittest.main()
