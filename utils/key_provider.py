"""Platform key stores with an explicit, observable file fallback."""
import base64
import os
import sys
import tempfile
from dataclasses import dataclass
from abc import ABC, abstractmethod

from utils.errors import KeyUnavailableError

_KEY_LEN = 32


class KeyProvider(ABC):
    @abstractmethod
    def load_key(self) -> bytes | None:
        """Return the existing key, or None when no key has been stored."""

    @abstractmethod
    def store_key(self, key: bytes) -> None:
        """Persist an explicit key without silently replacing another one."""

    @abstractmethod
    def get_or_create_key(self) -> bytes:
        """Returns a 32-byte AES-256 key. Generates and persists one on the
        first call if none exists; every later call returns THE SAME key.
        """

    @abstractmethod
    def replace_key(self, key: bytes, *, expected_current: bytes) -> None:
        """Atomically replace a known current key and verify persistence."""

    @abstractmethod
    def delete_key(self, *, expected_current: bytes) -> None:
        """Delete only the exact expected key."""


class FileKeyProvider(KeyProvider):
    """Keeps the key at the given file path, generating it ATOMICALLY on first use.

    Key creation uses `O_CREAT | O_EXCL`, so the "create if absent" check and
    the write are a single atomic step AT THE OPERATING-SYSTEM LEVEL. This is
    required: otherwise two processes could race between an `exists()` check
    and the write, both would generate a DIFFERENT random key, and the second
    write would silently overwrite the first. Everything the first process had
    encrypted with that key would become PERMANENTLY unrecoverable -- the
    discarded key is backed up nowhere.

    This scenario is not theoretical: the application has no process-level
    single-instance protection, so on a fresh installation double-clicking the
    desktop shortcut is enough. Ordinary user behaviour, not an attack.

    The side that LOSES the race does not error: it reads the key the winner
    wrote, and both processes continue with the same key.

    `O_EXCL` ALONE IS NOT ENOUGH; this was verified empirically. `O_EXCL`
    creates the file atomically, but between creation and the content being
    written the file is briefly visible as EMPTY. In a real concurrency test
    with 16 processes, the losers read in exactly that window and blew up with
    "Key file is corrupt: 0 bytes" -- so on its own `O_EXCL` did no more than
    turn "silent key destruction" into "crash at startup".

    That is why the content is written to a temporary file FIRST (flushed to
    disk with fsync), then linked atomically to the target path with
    `os.link`. `os.link` raises FileExistsError if the target exists and never
    overwrites. The result: the target path either does NOT exist at all, or
    exists with COMPLETE content -- no reader ever sees a half-written
    intermediate state.
    """

    def __init__(self, key_path: str):
        self._key_path = key_path

    def load_key(self) -> bytes | None:
        if not os.path.exists(self._key_path):
            return None
        return self._read_existing()

    def store_key(self, key: bytes) -> None:
        _validate_key(key)
        existing = self.load_key()
        if existing is not None:
            if existing != key:
                raise KeyUnavailableError(
                    "Mevcut anahtar doğrulanmadan değiştirilemez."
                )
            return
        self._create_atomically(key)

    def get_or_create_key(self) -> bytes:
        existing = self.load_key()
        if existing is not None:
            return existing
        key = os.urandom(_KEY_LEN)
        return self._create_atomically(key)

    def replace_key(self, key, *, expected_current):
        _validate_key(key)
        _validate_key(expected_current)
        if self.load_key() != expected_current:
            raise KeyUnavailableError(
                "Anahtar değişti; güvenli değiştirme iptal edildi."
            )
        directory = os.path.dirname(self._key_path) or "."
        fd, staged = tempfile.mkstemp(dir=directory, suffix=".replacement")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(key)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(staged, 0o600)
            os.replace(staged, self._key_path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
        if self.load_key() != key:
            raise KeyUnavailableError("Yeni anahtar yazımı doğrulanamadı.")

    def delete_key(self, *, expected_current):
        if self.load_key() != expected_current:
            raise KeyUnavailableError("Silinecek anahtar beklenen anahtar değil.")
        os.unlink(self._key_path)

    def _create_atomically(self, key):
        directory = os.path.dirname(self._key_path) or "."
        os.makedirs(directory, exist_ok=True)


        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=os.path.basename(self._key_path) + ".", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(key)
                f.flush()


                os.fsync(f.fileno())
            try:
                os.link(tmp_path, self._key_path)
            except FileExistsError:


                return self._read_existing()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        return key

    def _read_existing(self) -> bytes:
        with open(self._key_path, "rb") as f:
            key = f.read()
        if len(key) != _KEY_LEN:
            raise KeyUnavailableError(
                f"Anahtar dosyası bozuk: {len(key)} byte (beklenen {_KEY_LEN})."
            )
        return key


class KeyringKeyProvider(KeyProvider):
    """Secret Service/KWallet provider through the standard keyring API."""

    def __init__(self, service="Helyosfer", username="encryption-key",
                 keyring_module=None):
        self.service = service
        self.username = username
        if keyring_module is None:


            try:
                import keyring as _keyring
            except ImportError as exc:
                raise KeyUnavailableError(
                    "Linux güvenli anahtar deposu bağımlılığı bulunamadı."
                ) from exc
            keyring_module = _keyring
        self._keyring = keyring_module

    def is_available(self):
        try:
            backend = self._keyring.get_keyring()
            priority = getattr(backend, "priority", 0)
            return float(priority) > 0
        except (RuntimeError, TypeError, ValueError):
            return False

    def load_key(self):
        if not self.is_available():
            raise KeyUnavailableError("OS anahtar deposu kullanılamıyor.")
        try:
            encoded = self._keyring.get_password(
                self.service, self.username
            )
        except Exception as exc:
            raise KeyUnavailableError(
                "OS anahtar deposundan anahtar okunamadı."
            ) from exc
        if encoded is None:
            return None
        try:
            key = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise KeyUnavailableError(
                "OS anahtar deposundaki değer bozuk."
            ) from exc
        _validate_key(key)
        return key

    def store_key(self, key):
        _validate_key(key)
        existing = self.load_key()
        if existing is not None and existing != key:
            raise KeyUnavailableError(
                "Mevcut OS anahtarı doğrulanmadan değiştirilemez."
            )
        try:
            self._keyring.set_password(
                self.service,
                self.username,
                base64.b64encode(key).decode("ascii"),
            )
        except Exception as exc:
            raise KeyUnavailableError(
                "Anahtar OS güvenli deposuna yazılamadı."
            ) from exc
        if self.load_key() != key:
            raise KeyUnavailableError("OS anahtar deposu yazımı doğrulanamadı.")

    def get_or_create_key(self):
        key = self.load_key()
        if key is not None:
            return key
        key = os.urandom(_KEY_LEN)
        self.store_key(key)
        return key

    def replace_key(self, key, *, expected_current):
        _validate_key(key)
        if self.load_key() != expected_current:
            raise KeyUnavailableError(
                "OS anahtarı değişti; güvenli değiştirme iptal edildi."
            )
        try:
            self._keyring.set_password(
                self.service,
                self.username,
                base64.b64encode(key).decode("ascii"),
            )
        except Exception as exc:
            raise KeyUnavailableError(
                "OS anahtar deposundaki anahtar değiştirilemedi."
            ) from exc
        if self.load_key() != key:
            raise KeyUnavailableError(
                "OS anahtar deposundaki yeni anahtar doğrulanamadı."
            )

    def delete_key(self, *, expected_current):
        if self.load_key() != expected_current:
            raise KeyUnavailableError("Silinecek OS anahtarı eşleşmiyor.")
        try:
            self._keyring.delete_password(self.service, self.username)
        except Exception as exc:
            raise KeyUnavailableError(
                "OS anahtar deposundaki anahtar silinemedi."
            ) from exc


class DpapiKeyProvider(FileKeyProvider):
    """Windows DPAPI-protected blob bound to the current Windows user."""

    def __init__(self, key_path, protector=None):
        super().__init__(key_path)
        self._protector = protector or _WindowsDpapi()

    def _read_existing(self):
        with open(self._key_path, "rb") as stream:
            protected = stream.read()
        try:
            key = self._protector.unprotect(protected)
        except OSError as exc:
            raise KeyUnavailableError(
                "DPAPI anahtar blob'u açılamadı."
            ) from exc
        _validate_key(key)
        return key

    def _create_atomically(self, key):
        _validate_key(key)
        try:
            protected = self._protector.protect(key)
        except OSError as exc:
            raise KeyUnavailableError(
                "Anahtar DPAPI ile korunamadı."
            ) from exc
        stored = super()._create_atomically(protected)


        if stored is protected:
            return key
        return stored

    def replace_key(self, key, *, expected_current):
        _validate_key(key)
        if self.load_key() != expected_current:
            raise KeyUnavailableError(
                "DPAPI anahtarı değişti; işlem iptal edildi."
            )
        protected = self._protector.protect(key)


        directory = os.path.dirname(self._key_path) or "."
        fd, staged = tempfile.mkstemp(dir=directory, suffix=".replacement")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(protected)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(staged, self._key_path)
        finally:
            if os.path.exists(staged):
                os.unlink(staged)
        if self.load_key() != key:
            raise KeyUnavailableError("DPAPI anahtar değişimi doğrulanamadı.")


class _WindowsDpapi:
    def protect(self, data):
        return _dpapi_call(data, protect=True)

    def unprotect(self, data):
        return _dpapi_call(data, protect=False)


def _dpapi_call(data, *, protect):
    if sys.platform != "win32":
        raise OSError("DPAPI yalnız Windows üzerinde kullanılabilir.")
    import ctypes
    from ctypes import wintypes

    class DataBlob(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_ubyte)),
        ]

    raw = ctypes.create_string_buffer(data)
    source = DataBlob(
        len(data), ctypes.cast(raw, ctypes.POINTER(ctypes.c_ubyte))
    )
    destination = DataBlob()
    function = (
        ctypes.windll.crypt32.CryptProtectData
        if protect
        else ctypes.windll.crypt32.CryptUnprotectData
    )
    args = (
        (ctypes.byref(source), "Helyosfer key", None, None, None, 0,
         ctypes.byref(destination))
        if protect
        else (ctypes.byref(source), None, None, None, None, 0,
              ctypes.byref(destination))
    )
    if not function(*args):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(destination.pbData, destination.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(destination.pbData)


@dataclass(frozen=True)
class KeyProtectionStatus:
    method: str
    secure_store: bool
    warning: str | None = None


class MigratingKeyProvider(KeyProvider):
    """Move a legacy raw file into an available OS store, with verification."""

    def __init__(self, primary, fallback, status):
        self.primary = primary
        self.fallback = fallback
        self.status = status

    def load_key(self):
        if self.primary is None:
            return self.fallback.load_key()
        key = self.primary.load_key()
        if key is not None:
            return key
        legacy = self.fallback.load_key()
        if legacy is None:
            return None
        self.primary.store_key(legacy)
        if self.primary.load_key() != legacy:
            raise KeyUnavailableError(
                "Eski anahtarın OS deposuna geçişi doğrulanamadı."
            )
        os.unlink(self.fallback._key_path)
        return legacy

    def store_key(self, key):
        target = self.primary or self.fallback
        target.store_key(key)

    def get_or_create_key(self):
        key = self.load_key()
        if key is not None:
            return key
        key = os.urandom(_KEY_LEN)
        self.store_key(key)
        return key

    def replace_key(self, key, *, expected_current):
        target = self.primary or self.fallback
        target.replace_key(key, expected_current=expected_current)

    def delete_key(self, *, expected_current):
        target = self.primary or self.fallback
        target.delete_key(expected_current=expected_current)


def create_platform_key_provider(data_directory, *, keyring_module=None):
    fallback = FileKeyProvider(
        os.path.join(str(data_directory), "encryption.key")
    )
    if sys.platform == "win32":
        provider = DpapiKeyProvider(
            os.path.join(str(data_directory), "encryption.key.dpapi")
        )
        return MigratingKeyProvider(
            provider,
            fallback,
            KeyProtectionStatus("Windows DPAPI", True),
        )
    if sys.platform.startswith("linux"):
        try:
            provider = KeyringKeyProvider(keyring_module=keyring_module)
            if provider.is_available():
                return MigratingKeyProvider(
                    provider,
                    fallback,
                    KeyProtectionStatus("Linux Secret Service/KWallet", True),
                )
        except KeyUnavailableError:
            pass
        return MigratingKeyProvider(
            None,
            fallback,
            KeyProtectionStatus(
                "owner-only file",
                False,
                "OS anahtar deposu kullanılamıyor; anahtar 0600 izinli "
                "yerel dosyada saklanıyor.",
            ),
        )
    return MigratingKeyProvider(
        None,
        fallback,
        KeyProtectionStatus(
            "owner-only file",
            False,
            "Bu platformda desteklenen OS anahtar deposu yok.",
        ),
    )


def _validate_key(key):
    if not isinstance(key, bytes) or len(key) != _KEY_LEN:
        length = len(key) if isinstance(key, bytes) else "geçersiz"
        raise KeyUnavailableError(
            f"Anahtar bozuk: {length} byte (beklenen {_KEY_LEN})."
        )
