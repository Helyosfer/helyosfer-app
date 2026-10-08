"""The AEAD encryption core.

Versioned, authenticated encryption built on AES-256-GCM. It replaces
the legacy AES-CBC scheme (fixed key, no MAC, fail-open), which
`utils/crypto.py` still reads for old data. This file contains only the pure
encryption logic --
no assumption about the GUI or about where the key lives, so it is testable
entirely on its own.

Unlike the old `utils/crypto.py::decrypt()`, there is NO FAIL-OPEN here:
every failure raises `DecryptionError`. That is a deliberate design decision
("on decrypt failure, surface the error -- don't fail open"). The caller decides for itself how to handle it.

"""
import base64
import binascii
import os

from Crypto.Cipher import AES

_VERSION = 1
_ALGO_AES_256_GCM = 1
_HEADER_LEN = 2  # version + algo id
_NONCE_LEN = 12
_TAG_LEN = 16
_KEY_LEN = 32  # AES-256


class DecryptionError(Exception):
    """Decryption failed: wrong key, corrupt or tampered data, or an
    unrecognised version/algorithm. NO fail-open -- the caller sees the real
    error.
    """


def _require_key_length(key: bytes) -> None:
    if len(key) != _KEY_LEN:
        raise ValueError(f"Anahtar {_KEY_LEN} byte olmalı, {len(key)} byte verildi.")


def encrypt(plaintext: str, key: bytes) -> str:
    """Encrypts `plaintext` with AES-256-GCM; returns base64(version|algo|nonce|tag|ciphertext)."""
    _require_key_length(key)
    nonce = os.urandom(_NONCE_LEN)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))
    envelope = bytes([_VERSION, _ALGO_AES_256_GCM]) + nonce + tag + ciphertext
    return base64.b64encode(envelope).decode("utf-8")


def decrypt(token: str, key: bytes) -> str:
    """Unwraps the envelope produced by `encrypt()`. Raises `DecryptionError`
    on any inconsistency (tampered envelope, wrong key, unrecognised
    version/algorithm) -- there is NO silent substitute value.
    """
    _require_key_length(key)

    try:
        envelope = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError) as e:
        raise DecryptionError(f"Geçersiz base64: {e}") from e

    if len(envelope) < _HEADER_LEN + _NONCE_LEN + _TAG_LEN:
        raise DecryptionError("Zarf çok kısa — bozuk veya kurcalanmış veri.")

    version, algo_id = envelope[0], envelope[1]
    if version != _VERSION:
        raise DecryptionError(f"Bilinmeyen zarf versiyonu: {version}")
    if algo_id != _ALGO_AES_256_GCM:
        raise DecryptionError(f"Bilinmeyen algoritma id: {algo_id}")

    body = envelope[_HEADER_LEN:]
    nonce, tag, ciphertext = (
        body[:_NONCE_LEN],
        body[_NONCE_LEN:_NONCE_LEN + _TAG_LEN],
        body[_NONCE_LEN + _TAG_LEN:],
    )

    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    try:
        plaintext_bytes = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as e:


        raise DecryptionError(
            f"Kimlik doğrulama başarısız — yanlış anahtar ya da kurcalanmış veri: {e}"
        ) from e

    try:
        return plaintext_bytes.decode("utf-8")
    except UnicodeDecodeError as e:
        raise DecryptionError(f"Çözülen veri geçerli UTF-8 değil: {e}") from e
