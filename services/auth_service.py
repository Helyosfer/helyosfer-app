"""Local sign-in: first-time setup, login, forced renewal and password change.

The interface only shows what this service returns. Every decision -- is there
a usable credential, is the account throttled, does the password still meet
the policy -- is made here so it can be tested without a window.

The credential lives in the settings store under "security"; the failed
attempt counter under "security_throttle".
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from security.security_service import LoginThrottle, PasswordPolicy, SecurityService
from ui.i18n import tr, trf
from utils.logging_config import get_logger

SETUP = "setup"
LOGIN = "login"
RENEWAL = "renewal"
ACCOUNT_SETUP = "account_setup"
HOME = "home"


@dataclass(frozen=True)
class AuthResult:
    ok: bool
    screen: str
    message: str = ""


class AuthService:
    def __init__(self, store, *, now=None):
        self._store = store
        self._now = now
        self.renewal_required = False

    # -- state ---------------------------------------------------------------
    def credential_exists(self) -> bool:
        """Is there a usable password record? An unreadable one counts as none."""
        try:
            security = self._store.get("security")
        except (OSError, ValueError):
            get_logger().exception("Güvenlik kaydı okunamadı; kurulum ekranına düşülüyor")
            return False
        return bool(
            security.get("is_set") is True
            and security.get("pin_hash")
            and security.get("salt")
        )

    def start_screen(self) -> str:
        return LOGIN if self.credential_exists() else SETUP

    def screen_after_auth(self) -> str:
        from services.account_service import AccountService

        try:
            if not AccountService.has_any_account():
                return ACCOUNT_SETUP
        except (sqlite3.Error, OSError):
            get_logger().exception("Hesap kontrolü yapılamadı")
        return HOME

    # -- throttle ------------------------------------------------------------
    def _throttle_state(self) -> dict:
        return self._store.get("security_throttle")

    def seconds_locked(self) -> int:
        remaining = LoginThrottle.seconds_remaining(self._throttle_state(), self._now)
        return int(remaining) + 1 if remaining > 0 else 0

    def _throttled_message(self) -> str:
        return trf(
            "Çok fazla hatalı deneme. {seconds} saniye sonra tekrar deneyin.",
            seconds=self.seconds_locked(),
        )

    def _record_failure(self) -> None:
        state = LoginThrottle.record_failure(self._throttle_state(), self._now)
        self._store.put("security_throttle", **state)

    def _record_success(self) -> None:
        self._store.put("security_throttle", **LoginThrottle.record_success())

    def _save_password(self, password: str) -> None:
        salt = SecurityService.generate_salt()
        self._store.put(
            "security",
            pin_hash=SecurityService.hash_password(password, salt),
            salt=salt,
            is_set=True,
        )

    # -- flows ---------------------------------------------------------------
    def setup(self, password: str, confirmation: str) -> AuthResult:
        """First-time setup, or the forced renewal that follows a weak login."""
        current = RENEWAL if self.renewal_required else SETUP
        if self.credential_exists() and not self.renewal_required:
            return AuthResult(
                False, LOGIN, tr("Şifre değiştirmek için mevcut şifrenizi girin.")
            )
        valid, policy_error = PasswordPolicy.validate(password)
        if not valid:
            return AuthResult(False, current, tr(policy_error))
        if password != confirmation:
            return AuthResult(False, current, tr("Şifreler eşleşmiyor."))

        self._save_password(password)
        if self.renewal_required:
            self.renewal_required = False
            self._record_success()
            return AuthResult(True, LOGIN)
        return AuthResult(True, self.screen_after_auth())

    def login(self, password: str) -> AuthResult:
        if not self.credential_exists():
            return AuthResult(False, SETUP)
        if self.seconds_locked():
            return AuthResult(False, LOGIN, self._throttled_message())

        security = self._store.get("security")
        if not SecurityService.verify_password(
            password, security["salt"], security["pin_hash"]
        ):
            self._record_failure()
            message = (
                self._throttled_message() if self.seconds_locked()
                else tr("Hatalı Şifre!")
            )
            return AuthResult(False, LOGIN, message)

        self._record_success()
        if not PasswordPolicy.is_compliant(password):
            # Verified against the stored hash first, so a long-standing weak
            # password is never locked out -- it is sent to renewal instead.
            self.renewal_required = True
            return AuthResult(True, RENEWAL, tr(
                "Şifreniz güncel güvenlik politikasını karşılamıyor. "
                "Devam etmek için yeni bir şifre belirleyin."
            ))
        if SecurityService.needs_upgrade(security["pin_hash"]):
            self._store.put(
                "security",
                pin_hash=SecurityService.hash_password(password),
                salt=security["salt"],
                is_set=True,
            )
        return AuthResult(True, self.screen_after_auth())

    def change_password(self, current: str, password: str, confirmation: str) -> AuthResult:
        if self.seconds_locked():
            return AuthResult(False, HOME, self._throttled_message())

        security = self._store.get("security")
        stored_hash = security.get("pin_hash")
        if not stored_hash or not SecurityService.verify_password(
            current, security.get("salt"), stored_hash
        ):
            self._record_failure()
            return AuthResult(False, HOME, tr("Hatalı Şifre!"))

        valid, policy_error = PasswordPolicy.validate(password)
        if not valid:
            return AuthResult(False, HOME, tr(policy_error))
        if password != confirmation:
            return AuthResult(False, HOME, tr("Şifreler eşleşmiyor."))
        if password == current:
            return AuthResult(
                False, HOME, tr("Yeni şifre mevcut şifreyle aynı olamaz.")
            )

        self._save_password(password)
        self._record_success()
        return AuthResult(True, LOGIN, tr(
            "Şifre başarıyla değiştirildi. Lütfen tekrar giriş yapın."
        ))
