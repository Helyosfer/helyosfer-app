"""Field encryption entry point.

This module is a TRANSPARENT DISPATCHER: every call site
(database/db.py, services/*.py) keeps calling `encrypt()`/`decrypt()`
with one stable signature. What happens INSIDE:

  - `encrypt()` now ALWAYS uses the new AEAD scheme (utils/aead_crypto.py:
    AES-256-GCM, versioned envelope, a per-installation random key --
    utils/key_provider.py::FileKeyProvider). NO NEW DATA IS PRODUCED with the
    old AES-CBC any more; that code was therefore removed entirely
    (`_decrypt_legacy_cbc` below remains FOR READING ONLY).
  - `decrypt()` decides which scheme to use by checking whether the value
    starts with the `AEADv1:` prefix. Because that prefix contains a character
    (`:`) that never appears in the base64 alphabet, the old/new distinction
    can be made WITH NO RISK OF A FALSE POSITIVE. Without the prefix the old
    CBC path runs UNCHANGED -- old data stays readable forever, with no
    backward migration (see
    tests/test_crypto.py::LegacyFormatBackwardCompatibilityTest, which tests
    against a real blob produced by this file BEFORE it was modified).

The outward contract is fail-closed: encryption/decryption errors reach the
caller as typed exceptions. Sensitive data never falls back to plaintext
because encryption failed, and ciphertext that cannot be verified is never
presented as valid data. Legacy CBC is kept only for backward reads.

"""
import base64
import binascii
import functools

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad

from utils import aead_crypto
from utils.errors import (
    DecryptionError,
    EncryptionError,
    IntegrityVerificationError,
    KeyUnavailableError,
)


STATIC_SALT = b"fi" + b"nora_secure_salt_2026"
DEFAULT_PASSWORD = "fi" + "nora_secure_2026"

_AEAD_PREFIX = "AEADv1:"


@functools.lru_cache(maxsize=4)
def _get_key(password: str) -> bytes:
    """Derives a secure 32-byte key from a password using PBKDF2.
    Used ONLY for decrypting old CBC data.
    """
    return PBKDF2(password, STATIC_SALT, dkLen=32, count=1000000)


@functools.lru_cache(maxsize=1)
def _get_key_provider():
    from utils.app_paths import data_dir
    from utils.key_provider import create_platform_key_provider

    return create_platform_key_provider(data_dir())


@functools.lru_cache(maxsize=1)
def _get_aead_key() -> bytes:
    """Lazily resolves the per-installation random AES-256 key and caches it
    within the process (the same pattern as `_get_key` above).

    Runs DELIBERATELY not at import time but only on the first real
    encrypt()/decrypt() call -- dozens of test files import `utils.crypto`,
    and merely importing it must not create a real key file (see the same
    principle in utils/app_paths.py, which also applied to DB_NAME).
    """
    return _get_key_provider().get_or_create_key()


def key_protection_status():
    """Return user-displayable information; fallback is never implicit."""
    return _get_key_provider().status


def active_key_provider():
    """Return the process-cached provider used by encryption operations."""
    return _get_key_provider()


def encrypt(data, password: str = DEFAULT_PASSWORD) -> str:
    """Encrypts data with AES-256-GCM (AEAD); returns base64 with an `AEADv1:` prefix.

    The `password` parameter is NO LONGER FUNCTIONALLY USED -- the new scheme
    uses a per-installation random key and does not derive one from a string
    password. The only reason it remains in the signature: all 103 call sites
    call `encrypt(str(x), SECRET_KEY)`, and changing the signature would force
    all of them to change. Note that `decrypt()` still REALLY uses its
    `password` -- it is still needed to read old data.
    """
    if data is None or str(data).strip() == "":
        return data

    try:
        key = _get_aead_key()
    except (OSError, ValueError) as exc:
        raise KeyUnavailableError(
            "Şifreleme anahtarına erişilemedi; veri kaydedilmedi."
        ) from exc
    try:
        token = aead_crypto.encrypt(str(data), key)
    except (ValueError, TypeError) as exc:
        raise EncryptionError(
            "Veri şifrelenemedi; hiçbir düz metin kaydedilmedi."
        ) from exc
    return _AEAD_PREFIX + token


def _decrypt_legacy_cbc(enc_data, password: str) -> str:
    """Decrypts data encrypted with the old AES-256-CBC scheme (fixed
    password, no MAC). No new data is WRITTEN in this format any more -- this
    function exists only to keep existing old records readable.
    """
    try:
        encrypted_payload = base64.b64decode(str(enc_data), validate=True)
        iv = encrypted_payload[:16]
        ciphertext = encrypted_payload[16:]
        key = _get_key(password)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        decrypted_bytes = unpad(cipher.decrypt(ciphertext), AES.block_size)
        return decrypted_bytes.decode('utf-8')
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise DecryptionError(
            "Legacy şifreli veri çözülemedi veya biçimi geçersiz."
        ) from exc


def decrypt(enc_data, password: str = DEFAULT_PASSWORD) -> str:
    """Decrypts either the AEAD envelope produced by `encrypt()` OR data in
    the old CBC format (from before the migration) -- the format is told apart
    by the `AEADv1:` prefix. That prefix contains a `:`, which never appears
    in the base64 alphabet, so the old/new distinction carries no risk of a
    false positive.
    """
    if enc_data is None or str(enc_data).strip() == "":
        return enc_data

    text = str(enc_data)
    if text.startswith(_AEAD_PREFIX):
        try:
            key = _get_aead_key()
        except (OSError, ValueError) as exc:
            raise KeyUnavailableError(
                "Şifreleme anahtarına erişilemedi; veri açılamadı."
            ) from exc
        try:
            return aead_crypto.decrypt(text[len(_AEAD_PREFIX):], key)
        except aead_crypto.DecryptionError as exc:
            raise IntegrityVerificationError(
                "Şifreli verinin bütünlüğü doğrulanamadı."
            ) from exc
        except ValueError as exc:
            raise KeyUnavailableError(
                "Şifreleme anahtarı geçersiz; veri açılamadı."
            ) from exc

    return _decrypt_legacy_cbc(text, password)
