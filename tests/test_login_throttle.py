"""PIN attempt throttling -- the pure logic of
security.security_service.LoginThrottle. No test waits real seconds; `now` is
injected everywhere (see LoginThrottle's own docstring).
"""
import unittest

from security.security_service import LoginThrottle


class LockoutThresholdTest(unittest.TestCase):
    def test_no_lockout_below_threshold(self):
        for attempts in range(0, LoginThrottle.FAILED_ATTEMPT_THRESHOLD):
            state = {"failed_attempts": attempts, "last_failed_at": 1000.0}
            self.assertEqual(
                LoginThrottle.seconds_remaining(state, now=1000.0), 0.0,
                msg=f"{attempts} denemede kilit olmamalı",
            )
            self.assertFalse(LoginThrottle.is_locked(state, now=1000.0))

    def test_lockout_kicks_in_exactly_at_threshold(self):
        state = {
            "failed_attempts": LoginThrottle.FAILED_ATTEMPT_THRESHOLD,
            "last_failed_at": 1000.0,
        }
        self.assertTrue(LoginThrottle.is_locked(state, now=1000.0))
        self.assertGreater(
            LoginThrottle.seconds_remaining(state, now=1000.0), 0.0
        )

    def test_no_state_at_all_means_not_locked(self):
        """With no attempt record at all (the first login) there must be no lockout."""
        self.assertFalse(LoginThrottle.is_locked(None))
        self.assertFalse(LoginThrottle.is_locked({}))


class ExponentialBackoffTest(unittest.TestCase):
    def test_duration_grows_with_each_additional_attempt(self):
        durations = [
            LoginThrottle._lockout_duration(n)
            for n in range(
                LoginThrottle.FAILED_ATTEMPT_THRESHOLD,
                LoginThrottle.FAILED_ATTEMPT_THRESHOLD + 5,
            )
        ]
        for earlier, later in zip(durations, durations[1:]):
            self.assertLess(earlier, later)

    def test_duration_caps_at_max_even_with_many_attempts(self):
        huge = LoginThrottle._lockout_duration(1000)
        self.assertEqual(huge, LoginThrottle.LOCKOUT_MAX_SECONDS)


class ClockInjectionTest(unittest.TestCase):
    """The real point: can 'time passing' be simulated without any real
    time.sleep()?
    """

    def test_lockout_expires_after_enough_simulated_time_passes(self):
        state = LoginThrottle.record_failure({}, now=1000.0)
        for _ in range(LoginThrottle.FAILED_ATTEMPT_THRESHOLD - 1):
            state = LoginThrottle.record_failure(state, now=1000.0)
        self.assertTrue(LoginThrottle.is_locked(state, now=1000.0))

        duration = LoginThrottle._lockout_duration(state["failed_attempts"])
        still_locked_at = 1000.0 + duration - 1
        unlocked_at = 1000.0 + duration + 1

        self.assertTrue(LoginThrottle.is_locked(state, now=still_locked_at))
        self.assertFalse(LoginThrottle.is_locked(state, now=unlocked_at))

    def test_seconds_remaining_counts_down_linearly(self):
        state = {
            "failed_attempts": LoginThrottle.FAILED_ATTEMPT_THRESHOLD,
            "last_failed_at": 1000.0,
        }
        duration = LoginThrottle._lockout_duration(state["failed_attempts"])
        self.assertAlmostEqual(
            LoginThrottle.seconds_remaining(state, now=1000.0), duration,
        )
        self.assertAlmostEqual(
            LoginThrottle.seconds_remaining(state, now=1000.0 + duration / 2),
            duration / 2,
        )


class StateTransitionTest(unittest.TestCase):
    def test_record_failure_increments_and_does_not_mutate_input(self):
        original = {"failed_attempts": 2, "last_failed_at": 500.0}
        new_state = LoginThrottle.record_failure(original, now=999.0)

        self.assertEqual(original, {"failed_attempts": 2, "last_failed_at": 500.0})
        self.assertEqual(new_state["failed_attempts"], 3)
        self.assertEqual(new_state["last_failed_at"], 999.0)

    def test_record_failure_from_empty_state_starts_at_one(self):
        new_state = LoginThrottle.record_failure({}, now=1.0)
        self.assertEqual(new_state["failed_attempts"], 1)

    def test_record_success_resets_to_zero(self):
        state = LoginThrottle.record_success()
        self.assertEqual(state, {"failed_attempts": 0, "last_failed_at": None})
        self.assertFalse(LoginThrottle.is_locked(state, now=1_000_000.0))

    def test_full_cycle_lockout_then_success_resets_counter(self):
        """End to end: consecutive failed attempts cause a lockout; the following
        successful login resets the counters and it never again behaves as
        though the old attempt count had accumulated.
        """
        state = {}
        now = 0.0
        for _ in range(LoginThrottle.FAILED_ATTEMPT_THRESHOLD):
            state = LoginThrottle.record_failure(state, now=now)
        self.assertTrue(LoginThrottle.is_locked(state, now=now))

        state = LoginThrottle.record_success()
        self.assertFalse(LoginThrottle.is_locked(state, now=now))


        state = LoginThrottle.record_failure(state, now=now)
        self.assertFalse(LoginThrottle.is_locked(state, now=now))


if __name__ == "__main__":
    unittest.main()
