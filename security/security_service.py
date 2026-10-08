"""Password hashing service (for login verification).

NOTE: data encryption does NOT live here; it is in utils/crypto.py
(AES-256-CBC). This file used to contain Fernet-based encrypt_data/
decrypt_data as well; although no data was ever written to the database with
Fernet, the read side used it by mistake and could not decrypt descriptions.
The Fernet part was removed so that a single encryption system remains (see
utils/crypto.py).

FIX: the PIN used to be hashed with a
single round of salted SHA-256. A salt protects against rainbow tables but
does NOT MAKE THE COMPUTATION EXPENSIVE -- the possible combinations of a
4-6 digit PIN can be tried offline within seconds. Moved to Argon2id
(memory-hard, meaningfully slowing GPU/ASIC brute force).

BACKWARD COMPATIBILITY: existing users' hashes are still on disk in the old
SHA-256 format. `verify_password` recognises both formats (Argon2id hashes
are self-describing: they start with "$argon2id$"; SHA-256 is exactly 64 hex
characters). New hashes are always Argon2id -- `hash_password` now produces
only Argon2id. When a user logs in successfully with the old format,
`needs_upgrade()` returns True; on seeing that the caller silently
re-hashes the PIN to Argon2id and stores it -- the user notices nothing and
does not have to re-enter their PIN.

"""
import hashlib
import hmac
import secrets
import time as _time

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHash, VerifyMismatchError


_hasher = PasswordHasher()


_LEGACY_SHA256_LENGTH = 64


class SecurityService:

    @staticmethod
    def generate_salt():
        """Generates a cryptographically secure salt for each local profile.

        KEPT FOR BACKWARD COMPATIBILITY: first-time setup still calls and
        stores this (it is needed to verify old records), but new Argon2id
        hashes generate and store their own salt internally -- the value this
        function produces is not used for NEW hashes.
        """
        return secrets.token_hex(16)

    @staticmethod
    def hash_password(password, salt=None):
        """Hashes the PIN with Argon2id; the plain PIN is never stored.

        The `salt` parameter is accepted only for compatibility with the old
        call signature and is NOT USED -- Argon2id generates its own random
        salt and embeds it in the hash string it returns, so there is nothing
        extra to manage.
        """
        del salt
        return _hasher.hash(str(password))

    @staticmethod
    def _is_legacy_sha256(hashed_password):
        h = str(hashed_password)
        return len(h) == _LEGACY_SHA256_LENGTH and all(
            c in "0123456789abcdef" for c in h.lower()
        )

    @staticmethod
    def verify_password(plain_password, salt, hashed_password):
        """Verifies the entered PIN with a constant-time comparison.

        Recognises both the old (SHA-256+salt) and the new (Argon2id) format
        -- which one it is follows from the shape of `hashed_password` itself,
        so the caller does not need to know.
        """
        if SecurityService._is_legacy_sha256(hashed_password):
            payload = (str(salt) + str(plain_password)).encode("utf-8")
            candidate = hashlib.sha256(payload).hexdigest()
            return hmac.compare_digest(candidate, str(hashed_password))

        try:
            _hasher.verify(str(hashed_password), str(plain_password))
            return True
        except VerifyMismatchError:
            return False
        except InvalidHash:


            return False

    @staticmethod
    def needs_upgrade(hashed_password):
        """Is this hash in the old (SHA-256) format? If True, immediately after
        a successful verification the caller should re-hash with
        `hash_password` and store it (lazy migration -- the user notices
        nothing).
        """
        return SecurityService._is_legacy_sha256(hashed_password)


class PasswordPolicy:
    """The SINGLE policy source for the input side.

    Argon2id and `LoginThrottle` protect only THE HASH and THE ATTEMPT RATE.
    If the input itself is short and drawn from a narrow character set, the
    search space stays small and both are rendered meaningless: the old
    policy asked for 4 characters plus one uppercase and one special
    character, so `A!!!` was a valid password.

    Policy: at least 12 characters, with uppercase, lowercase, digit AND
    special character, ALL of them.

    LEADING/TRAILING WHITESPACE IS REJECTED EXPLICITLY, not trimmed silently.
    The old behaviour was `.strip()` in the callers: the user typed one
    password, the application stored A DIFFERENT one, and never told them.
    There were two honest options -- use the raw text consistently, or reject
    the whitespace; the second was chosen, because a user cannot verify that
    an invisible character is part of their password.

    First-time setup, password change, forced renewal and re-setup after a
    reset all go through here.
    """

    MIN_LENGTH = 12


    MAX_LENGTH = 64

    SPECIAL_CHARS = ".,;:!?-_@#$%^&*()+=/\\|~`'\"<>[]{}"


    TOO_SHORT = "Şifre en az 12 karakter olmalıdır."
    TOO_LONG = "Şifre en fazla 64 karakter olabilir."
    NO_UPPER = "Şifre en az 1 büyük harf içermelidir."
    NO_LOWER = "Şifre en az 1 küçük harf içermelidir."
    NO_DIGIT = "Şifre en az 1 rakam içermelidir."
    NO_SPECIAL = "Şifre en az 1 özel karakter (örn. . veya ,) içermelidir."
    HAS_EDGE_WHITESPACE = "Şifre başında veya sonunda boşluk içeremez."


    REQUIREMENTS = (
        "12-64 karakter, 1 büyük harf, 1 küçük harf, 1 rakam ve 1 özel karakter"
    )

    MESSAGES = (
        TOO_SHORT, TOO_LONG, NO_UPPER, NO_LOWER, NO_DIGIT, NO_SPECIAL,
        HAS_EDGE_WHITESPACE,
    )

    @staticmethod
    def validate(password):
        """Returns (is_valid, error_message).

        `error_message` is None when valid, otherwise one of the Turkish
        source strings in `MESSAGES`.
        """
        password = password or ""
        if password != password.strip():
            return False, PasswordPolicy.HAS_EDGE_WHITESPACE
        if len(password) < PasswordPolicy.MIN_LENGTH:
            return False, PasswordPolicy.TOO_SHORT
        if len(password) > PasswordPolicy.MAX_LENGTH:
            return False, PasswordPolicy.TOO_LONG
        if not any(c.isupper() for c in password):
            return False, PasswordPolicy.NO_UPPER
        if not any(c.islower() for c in password):
            return False, PasswordPolicy.NO_LOWER
        if not any(c.isdigit() for c in password):
            return False, PasswordPolicy.NO_DIGIT
        if not any(c in PasswordPolicy.SPECIAL_CHARS for c in password):
            return False, PasswordPolicy.NO_SPECIAL
        return True, None

    @staticmethod
    def is_compliant(password):
        """Yes or no only -- for the forced-renewal decision."""
        return PasswordPolicy.validate(password)[0]


class LoginThrottle:
    """Increasing delay/temporary lockout after consecutive failed PIN
    attempts (kept separate from Argon2id hashing).

    PURE LOGIC: the state (attempt count + last failure time) is supplied
    externally and returned -- this class persists nothing on its own;
    the caller keeps the state in the config record "security_throttle". `now` is injectable everywhere (defaulting to
    `time.time()`) -- tests can simulate clock manipulation without waiting
    real seconds.

    DECISION -- the lockout state is PERSISTENT: it is stored in
    `config_store` and is NOT RESET when the application restarts. A
    deliberate choice: this is a threat model aimed at an attacker with
    physical/file access to the device -- a temporary (memory-only) counter
    could be bypassed trivially by restarting the application, which would
    make the whole mechanism meaningless.

    Policy: NO delay for the first `FAILED_ATTEMPT_THRESHOLD` attempts (a
    tolerance for mistyping -- penalising every PIN entry would be poor UX).
    After the threshold, an exponentially increasing lockout:
    2^(attempts - threshold) * base seconds, up to the `LOCKOUT_MAX_SECONDS`
    ceiling.
    """

    FAILED_ATTEMPT_THRESHOLD = 3
    LOCKOUT_BASE_SECONDS = 5
    LOCKOUT_MAX_SECONDS = 300  # 5 dakika tavan

    @staticmethod
    def _lockout_duration(failed_attempts):
        if failed_attempts < LoginThrottle.FAILED_ATTEMPT_THRESHOLD:
            return 0
        exponent = failed_attempts - LoginThrottle.FAILED_ATTEMPT_THRESHOLD
        seconds = LoginThrottle.LOCKOUT_BASE_SECONDS * (2 ** exponent)
        return min(seconds, LoginThrottle.LOCKOUT_MAX_SECONDS)

    @staticmethod
    def seconds_remaining(state, now=None):
        """`state`: {"failed_attempts": int, "last_failed_at": float|None}.
        Returns 0.0 if the lockout has expired or never existed.
        """
        if now is None:
            now = _time.time()
        state = state or {}
        failed_attempts = int(state.get("failed_attempts", 0) or 0)
        last_failed_at = state.get("last_failed_at")
        duration = LoginThrottle._lockout_duration(failed_attempts)
        if duration == 0 or last_failed_at is None:
            return 0.0
        elapsed = now - float(last_failed_at)
        return max(0.0, duration - elapsed)

    @staticmethod
    def is_locked(state, now=None):
        return LoginThrottle.seconds_remaining(state, now=now) > 0

    @staticmethod
    def record_failure(state, now=None):
        """Returns the NEW state after a failed attempt (does not mutate the
        input).
        """
        if now is None:
            now = _time.time()
        state = state or {}
        failed_attempts = int(state.get("failed_attempts", 0) or 0) + 1
        return {"failed_attempts": failed_attempts, "last_failed_at": now}

    @staticmethod
    def record_success():
        """The reset state after a successful login."""
        return {"failed_attempts": 0, "last_failed_at": None}
