"""Verified, password-protected backup and rollback-safe restore."""

import base64
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
import hmac
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Hash import SHA256

from database.db import DB_NAME
from utils import aead_crypto
from utils.app_paths import data_dir
from utils.errors import (
    DataMigrationError,
    IntegrityVerificationError,
    KeyUnavailableError,
)

BACKUP_FORMAT_VERSION = 1
_RECOVERY_ITERATIONS = 600_000
_SALT_LEN = 16
_NONCE_LEN = 12
_KEY_LEN = 32
_AEAD_PREFIX = "AEADv1:"
_AUTH_CONTEXT = b"helyosfer-backup-auth-v2"


SUPPORTED_RECOVERY_KDF = "PBKDF2-HMAC-SHA256"
MIN_RECOVERY_ITERATIONS = 100_000
MAX_RECOVERY_ITERATIONS = 4_000_000


MAX_PACKAGE_MEMBERS = 4


MAX_DB_MEMBER_BYTES = 256 * 1024 * 1024


MAX_SMALL_MEMBER_BYTES = 4 * 1024 * 1024

MAX_TOTAL_BYTES = MAX_DB_MEMBER_BYTES + 3 * MAX_SMALL_MEMBER_BYTES


MAX_COMPRESSION_RATIO = 200

_REQUIRED_MEMBERS = ("finance.db", "metadata.json", "key.recovery.json")
_OPTIONAL_MEMBERS = ("config.json",)
_ALLOWED_MEMBERS = frozenset(_REQUIRED_MEMBERS + _OPTIONAL_MEMBERS)
_STAGE_CHUNK = 64 * 1024


_HASH_CHUNK = 1024 * 1024


def _sha256_file(path):
    """Computes the file's SHA-256 with CONSTANT memory.

    It used to read `hashlib.sha256(path.read_bytes()).hexdigest()`.
    `read_bytes()` pulls the WHOLE file into memory as an additional `bytes`
    object, and since the package limit is 256 MiB that meant a quarter of a
    gigabyte allocated for a single hash. Measured (a 64 MiB file):

        read_bytes : peak allocation ~67,109,000 bytes  (1.00x the file size)
        streaming  : peak allocation ~1,049,000 bytes   (0.02x)

    The digest stays BYTE FOR BYTE THE SAME; only the way it is read into
    memory changes.

    The file handle closes with `with`, so it is not leaked on error paths
    either -- a handle left open on Windows would block the next
    `os.replace`/delete step.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _member_byte_limit(name):
    return MAX_DB_MEMBER_BYTES if name == "finance.db" else MAX_SMALL_MEMBER_BYTES


def _require_plain_member_name(name):
    r"""The member name has to be a plain file name INSIDE the staging directory.

    Both `/` and `\` are tested as separators: the ZIP standard says `/`, but
    `\` is also seen in archives produced on Windows, and `Path(...).parts`
    does not treat it as a separator on POSIX -- so looking only at `Path`
    would have taken the name `..\finance.db` for A PLAIN NAME on Linux.
    """
    if not name or name in (".", ".."):
        raise IntegrityVerificationError(
            "Backup paketi güvenli olmayan dosya yolu içeriyor."
        )
    if "/" in name or "\\" in name:
        raise IntegrityVerificationError(
            "Backup paketi güvenli olmayan dosya yolu içeriyor."
        )
    if Path(name).is_absolute() or (len(name) >= 2 and name[1] == ":"):
        raise IntegrityVerificationError(
            "Backup paketi güvenli olmayan dosya yolu içeriyor."
        )


def _reject_unsafe_members(infos):
    """The pre-check that runs BEFORE a single byte is extracted."""
    if len(infos) > MAX_PACKAGE_MEMBERS:
        raise IntegrityVerificationError(
            "Backup paketi beklenenden fazla dosya içeriyor."
        )
    names = [info.filename for info in infos]
    if len(set(names)) != len(names):
        raise IntegrityVerificationError(
            "Backup paketi beklenmeyen veya yinelenen dosya içeriyor."
        )
    present = set(names)
    if not set(_REQUIRED_MEMBERS) <= present:
        raise IntegrityVerificationError(
            "Backup paketi gerekli dosyaları içermiyor."
        )
    if present - _ALLOWED_MEMBERS:
        raise IntegrityVerificationError(
            "Backup paketi beklenmeyen veya yinelenen dosya içeriyor."
        )

    declared_total = 0
    for info in infos:
        name = info.filename
        if info.is_dir() or name.endswith("/"):
            raise IntegrityVerificationError(
                "Backup paketi dizin girdisi içeriyor."
            )


        if info.flag_bits & 0x1:
            raise IntegrityVerificationError(
                "Backup paketi şifreli üye içeriyor."
            )


        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            raise IntegrityVerificationError(
                "Backup paketi sembolik bağ içeriyor."
            )
        limit = _member_byte_limit(name)
        if info.file_size > limit:
            raise IntegrityVerificationError(
                "Backup paketindeki bir dosya boyut sınırını aşıyor."
            )
        declared_total += info.file_size
        if info.compress_size > 0 and (
            info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
        ):
            raise IntegrityVerificationError(
                "Backup paketinin sıkıştırma oranı güvenli sınırın üzerinde."
            )
    if declared_total > MAX_TOTAL_BYTES:
        raise IntegrityVerificationError(
            "Backup paketinin toplam boyutu sınırı aşıyor."
        )


def _stage_member(archive, info, destination, running_total):
    """Copies a member with a BOUNDED stream, counting the bytes actually read.

    `archive.extract` is NOT USED. There are two reasons: (1) it derives the
    target path from the name inside the ZIP, which means delegating path
    safety to the library; (2) it writes without measuring the size -- the
    header's `file_size` can lie, and that lie is only discovered while writing
    to disk. Hence a SECOND counter here: the pre-check looks at the DECLARED
    size, this loop at the bytes ACTUALLY READ.
    """
    limit = _member_byte_limit(info.filename)
    written = 0
    target = destination / info.filename
    with archive.open(info, "r") as source, io.open(target, "wb") as sink:
        while True:
            chunk = source.read(_STAGE_CHUNK)
            if not chunk:
                break
            written += len(chunk)
            if written > limit:
                raise IntegrityVerificationError(
                    "Backup paketindeki bir dosya boyut sınırını aşıyor."
                )
            if running_total + written > MAX_TOTAL_BYTES:
                raise IntegrityVerificationError(
                    "Backup paketinin toplam boyutu sınırı aşıyor."
                )
            sink.write(chunk)
    return written


def _stage_package(package_path, destination):
    """Extracts the package ONCE, in a bounded way. Returns the staged member names.

    The SHARED entry point for verification and restore. `restore_backup` used
    to extract the package itself and then `verify_backup` extracted the same
    package a second time -- the same hostile input was being processed
    twice.
    """
    destination.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        with zipfile.ZipFile(package_path, "r") as archive:
            infos = archive.infolist()
            _reject_unsafe_members(infos)


            for info in infos:
                _require_plain_member_name(info.filename)
            total = 0
            for info in infos:
                total += _stage_member(archive, info, destination, total)
                staged.append(info.filename)
    except (
        zipfile.BadZipFile, zipfile.LargeZipFile, OSError, EOFError,
        ValueError,


        NotImplementedError, RuntimeError,
    ) as exc:


        raise IntegrityVerificationError("Backup paketi açılamadı.") from exc
    return staged


_HEX64 = frozenset("0123456789abcdef")


def _require_mapping(payload, label):
    """Verifies that the JSON root really is an object.

    A package whose `metadata.json` content was `[]` raised `AttributeError`
    on the `metadata.get(...)` call -- measured. The contract says
    `IntegrityVerificationError`; the root type has to be the first thing
    tested.
    """
    if not isinstance(payload, dict):
        raise IntegrityVerificationError(f"Backup {label} bozuk.")
    return payload


def _require_hex_digest(value, label):
    """A 64-character lowercase hex string -- the only valid representation of SHA-256."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or not set(value).issubset(_HEX64)
    ):
        raise IntegrityVerificationError(f"Backup {label} biçimi geçersiz.")
    return value


def _require_record_count(value):
    """`aead_records_verified` must be a REAL, non-negative `int`.

    It used to read `int(metadata.get("aead_records_verified", -1))`, and it
    was measured: `"abc"` raised `ValueError` and `None` raised `TypeError` --
    both outside the contract. `bool` is also excluded because it is a
    subclass of `int`: `True` would silently become the number 1.
    """
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise IntegrityVerificationError(
            "Backup AEAD doğrulama sayısı geçersiz."
        )
    return value

ENCRYPTED_FIELDS = {
    "transactions": ("amount", "description"),
    "active_debts": ("debt_name", "total_amount", "monthly_payment"),
    "active_assets": ("purchase_price", "quantity"),
    "recurring_payments": ("name", "amount"),
    "savings_goals": ("goal_name",),
    "installment_plans": ("description", "total_amount", "monthly_amount"),


    "savings_migration_quarantine": ("goal_name", "payload"),
}


def _key_provider(key_path=None, provider=None):
    if provider is not None:
        return provider
    if key_path is not None:
        from utils.key_provider import FileKeyProvider

        return FileKeyProvider(str(key_path))
    from utils.key_provider import create_platform_key_provider

    return create_platform_key_provider(data_dir())


def _require_passphrase(passphrase):
    if not isinstance(passphrase, str) or len(passphrase) < 12:
        raise ValueError("Kurtarma parolası en az 12 karakter olmalıdır.")


def encrypt_recovery_material(key, passphrase):
    _require_passphrase(passphrase)
    if len(key) != _KEY_LEN:
        raise KeyUnavailableError("Yedeklenecek şifreleme anahtarı geçersiz.")
    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    wrapping_key = PBKDF2(
        passphrase.encode("utf-8"),
        salt,
        dkLen=_KEY_LEN,
        count=_RECOVERY_ITERATIONS,
        hmac_hash_module=SHA256,
    )
    cipher = AES.new(wrapping_key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(key)
    return {
        "kdf": SUPPORTED_RECOVERY_KDF,
        "iterations": _RECOVERY_ITERATIONS,
        "salt": base64.b64encode(salt).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "tag": base64.b64encode(tag).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def _recovery_iterations(payload):
    """Bounds the round count coming from the package BEFORE HANDING IT to PBKDF2.

    `isinstance(value, bool)` is also excluded: `bool` is a subclass of `int`
    in Python, so `True` would pass a type check and be silently accepted as a
    single-round KDF.
    """
    value = payload.get("iterations")
    if isinstance(value, bool) or not isinstance(value, int):
        raise IntegrityVerificationError(
            "Backup kurtarma materyalinin tur sayısı geçersiz."
        )
    if not MIN_RECOVERY_ITERATIONS <= value <= MAX_RECOVERY_ITERATIONS:
        raise IntegrityVerificationError(
            "Backup kurtarma materyalinin tur sayısı desteklenen aralıkta değil."
        )
    return value


def decrypt_recovery_material(payload, passphrase):
    _require_passphrase(passphrase)
    if not isinstance(payload, dict):
        raise IntegrityVerificationError("Backup kurtarma materyali bozuk.")


    if payload.get("kdf") != SUPPORTED_RECOVERY_KDF:
        raise IntegrityVerificationError(
            "Backup kurtarma materyalinin KDF'i desteklenmiyor."
        )
    iterations = _recovery_iterations(payload)
    try:
        salt = base64.b64decode(payload["salt"], validate=True)
        nonce = base64.b64decode(payload["nonce"], validate=True)
        tag = base64.b64decode(payload["tag"], validate=True)
        ciphertext = base64.b64decode(payload["ciphertext"], validate=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise IntegrityVerificationError(
            "Backup kurtarma materyali bozuk."
        ) from exc


    if (
        len(salt) != _SALT_LEN
        or len(nonce) != _NONCE_LEN
        or len(tag) != 16
        or len(ciphertext) != _KEY_LEN
    ):
        raise IntegrityVerificationError(
            "Backup kurtarma materyalinin alan uzunlukları geçersiz."
        )
    wrapping_key = PBKDF2(
        passphrase.encode("utf-8"),
        salt,
        dkLen=_KEY_LEN,
        count=iterations,
        hmac_hash_module=SHA256,
    )
    try:
        cipher = AES.new(wrapping_key, AES.MODE_GCM, nonce=nonce)
        key = cipher.decrypt_and_verify(ciphertext, tag)
    except ValueError as exc:
        raise IntegrityVerificationError(
            "Backup parolası yanlış veya kurtarma materyali bozuk."
        ) from exc
    if len(key) != _KEY_LEN:
        raise IntegrityVerificationError("Backup anahtar uzunluğu geçersiz.")
    return key


def _backup_auth_tag(metadata, passphrase):
    """HMAC metadata with a passphrase-derived, domain-separated key."""
    material = dict(metadata)
    material.pop("authentication_tag", None)
    try:
        salt = base64.b64decode(material["authentication_salt"], validate=True)
    except (KeyError, ValueError, TypeError) as exc:
        raise IntegrityVerificationError("Backup authentication metadata bozuk.") from exc
    key = PBKDF2(passphrase.encode("utf-8"), _AUTH_CONTEXT + salt, dkLen=32,
                 count=_RECOVERY_ITERATIONS, hmac_hash_module=SHA256)
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(key, encoded, hashlib.sha256).hexdigest()


def _sqlite_backup(source_path, destination_path):
    source_uri = f"file:{Path(source_path).resolve()}?mode=ro"
    with closing(sqlite3.connect(source_uri, uri=True)) as source:
        with closing(sqlite3.connect(destination_path)) as destination:
            source.backup(destination)


def _integrity_check(db_path):
    with closing(sqlite3.connect(db_path)) as conn:
        result = conn.execute("PRAGMA integrity_check").fetchone()[0]


        cursor = conn.execute("PRAGMA foreign_key_check")
        try:
            violations = [tuple(row)[:3] for row in cursor.fetchmany(1)]
        finally:
            cursor.close()
    if result != "ok":
        raise IntegrityVerificationError(
            "Backup veritabanı SQLite bütünlük kontrolünü geçemedi."
        )
    if violations:
        table, rowid, parent = violations[0]
        raise IntegrityVerificationError(
            "Backup veritabanında foreign key ihlali var "
            f"(ilk: {table} rowid={rowid} -> {parent})."
        )


def _existing_tables(conn):
    return {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def verify_database_key(db_path, key):
    """Authenticate every AEAD field in the database with an explicit key."""
    checked = 0
    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        tables = _existing_tables(conn)
        for table, fields in ENCRYPTED_FIELDS.items():
            if table not in tables:
                continue
            columns = {
                row[1] for row in conn.execute(f"PRAGMA table_info({table})")
            }
            usable = [field for field in fields if field in columns]
            if not usable:
                continue
            selected = ", ".join(["id", *usable])
            for row in conn.execute(f"SELECT {selected} FROM {table}"):
                for field in usable:
                    value = row[field]
                    if value is None or str(value).strip() == "":
                        continue
                    text = str(value)
                    if not text.startswith(_AEAD_PREFIX):
                        continue
                    try:
                        aead_crypto.decrypt(
                            text[len(_AEAD_PREFIX):], key
                        )
                    except (aead_crypto.DecryptionError, ValueError) as exc:
                        raise IntegrityVerificationError(
                            f"Backup anahtarı {table} id={row['id']} "
                            f"field={field} kaydıyla eşleşmiyor."
                        ) from exc
                    checked += 1
    return checked


def create_backup(
    destination,
    passphrase,
    *,
    db_path=DB_NAME,
    key_path=None,
    key_provider=None,
    config_path=None,
):
    """Create a self-contained backup and verify it before publication."""
    db_path = Path(db_path)
    destination = Path(destination)
    if not db_path.is_file():
        raise FileNotFoundError("Yedeklenecek veritabanı bulunamadı.")
    provider = _key_provider(key_path, key_provider)
    key = provider.load_key()
    if key is None:
        raise KeyUnavailableError("Yedeklenecek şifreleme anahtarı bulunamadı.")
    recovery = encrypt_recovery_material(key, passphrase)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="helyosfer-backup-", dir=str(destination.parent)
    ) as temp_dir:
        temp = Path(temp_dir)
        db_copy = temp / "finance.db"
        _sqlite_backup(db_path, db_copy)
        _integrity_check(db_copy)
        aead_checked = verify_database_key(db_copy, key)
        metadata = {
            "format_version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database_sha256": _sha256_file(db_copy),
            "key_fingerprint": hashlib.sha256(key).hexdigest(),
            "aead_records_verified": aead_checked,
            "authentication_salt": base64.b64encode(os.urandom(16)).decode("ascii"),
        }
        metadata["authentication_tag"] = _backup_auth_tag(metadata, passphrase)
        (temp / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        (temp / "key.recovery.json").write_text(
            json.dumps(recovery, indent=2), encoding="utf-8"
        )
        members = ["finance.db", "metadata.json", "key.recovery.json"]
        if config_path and Path(config_path).is_file():
            shutil.copy2(config_path, temp / "config.json")
            members.append("config.json")

        staged = temp / "backup.zip"
        with zipfile.ZipFile(staged, "w", zipfile.ZIP_DEFLATED) as archive:
            for member in members:
                archive.write(temp / member, member)
        os.replace(staged, destination)

    verify_backup(destination, passphrase)
    return {
        "path": str(destination),
        "aead_records_verified": aead_checked,
        "database_sha256": metadata["database_sha256"],
    }


def _verify_staged(temp, passphrase):
    """Verifies a staged package (extracted and past the bounds checks).

    SEPARATE from `_stage_package` so that both `verify_backup` and
    `restore_backup` can use the same staging. Not extracting the package a
    second time is the sole purpose of the split.
    """
    try:
        metadata = json.loads(
            (temp / "metadata.json").read_text(encoding="utf-8")
        )
        recovery = json.loads(
            (temp / "key.recovery.json").read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise IntegrityVerificationError(
            "Backup metadata veya kurtarma materyali bozuk."
        ) from exc


    metadata = _require_mapping(metadata, "metadata")
    recovery = _require_mapping(recovery, "kurtarma materyali")


    version = metadata.get("format_version")
    if (
        isinstance(version, bool)
        or not isinstance(version, int)
        or version != 2
    ):
        raise IntegrityVerificationError("Backup format sürümü desteklenmiyor.")
    if not isinstance(metadata.get("authentication_salt"), str):
        raise IntegrityVerificationError("Backup authentication metadata bozuk.")
    expected_digest = _require_hex_digest(
        metadata.get("database_sha256"), "veritabanı hash'i")
    expected_fingerprint = _require_hex_digest(
        metadata.get("key_fingerprint"), "anahtar parmak izi")
    expected_records = _require_record_count(
        metadata.get("aead_records_verified"))

    supplied_tag = metadata.get("authentication_tag")
    if not isinstance(supplied_tag, str) or not hmac.compare_digest(
        supplied_tag, _backup_auth_tag(metadata, passphrase)
    ):
        raise IntegrityVerificationError("Backup authentication doğrulanamadı.")
    db_copy = temp / "finance.db"
    if _sha256_file(db_copy) != expected_digest:
        raise IntegrityVerificationError("Backup veritabanı hash'i eşleşmiyor.")
    key = decrypt_recovery_material(recovery, passphrase)
    if hashlib.sha256(key).hexdigest() != expected_fingerprint:
        raise IntegrityVerificationError("Backup anahtar parmak izi eşleşmiyor.")
    _integrity_check(db_copy)
    checked = verify_database_key(db_copy, key)
    if checked != expected_records:
        raise IntegrityVerificationError(
            "Backup AEAD doğrulama sayısı eşleşmiyor."
        )
    return {
        "key": key,
        "metadata": metadata,
        "config": (
            (temp / "config.json").read_bytes()
            if (temp / "config.json").exists()
            else None
        ),
    }


def verify_backup(package_path, passphrase):
    """Stage into a bounded temporary directory and prove DB/key compatibility."""
    package_path = Path(package_path)
    with tempfile.TemporaryDirectory(prefix="helyosfer-verify-") as temp_dir:
        temp = Path(temp_dir)
        _stage_package(package_path, temp)
        return _verify_staged(temp, passphrase)


_JOURNAL_DIRNAME = ".helyosfer-restore"
_JOURNAL_NAME = "journal.json"


_ROLLBACK_STATES = (
    "STAGED",
    "ROLLBACK_GENERATION_READY",
    "DB_REPLACED",
    "KEY_REPLACED",
    "CONFIG_REPLACED",
    "VERIFIED",
)


_COMMITTED_STATES = (
    "COMMITTED",
    "CLEANUP_COMPLETE",
)
_JOURNAL_STATES = _ROLLBACK_STATES + _COMMITTED_STATES


def _restore_journal_dir(db_path):
    return Path(db_path).parent / _JOURNAL_DIRNAME


def _savings_json_path(db_path):
    """The legacy goals file that is part of the restore generation.

    This file is NO LONGER A DATA SOURCE (goals live in finance.db), but it
    can still be sitting on disk. Because restore replaces the database
    wholesale, any JSON left over from it belongs by definition to the
    PREVIOUS generation; unless it is handled within the same generation, two
    generations get mixed together.
    """
    return Path(db_path).parent / "savings_goals.json"


def _write_journal(journal_dir, state, db_path, config, had_config,
                   had_savings_json=False):
    """Write the journal ATOMICALLY: a temporary file plus os.replace.

    Writing directly would leave a half-written or corrupt journal if the
    process died on exactly this line, and recovery would not know what to
    trust.

    `had_savings_json` was added to the EXISTING journal; A SECOND, PARALLEL
    JOURNAL WAS NOT OPENED. Two journals would mean two separate recovery
    paths and a state in which they could disagree.
    """
    payload = {
        "state": state,
        "db_path": str(db_path),
        "config_path": str(config) if config else None,
        "had_config": bool(had_config),
        "had_savings_json": bool(had_savings_json),
    }
    target = journal_dir / _JOURNAL_NAME
    fd, staged = tempfile.mkstemp(dir=str(journal_dir), prefix=".journal-")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staged, target)
    os.chmod(target, 0o600)


def _rollback_config(config, old_config, had_config):
    """Returns the config to its pre-restore state.

    The `had_config` distinction is essential: if there was NO config before
    the restore, the file the restore wrote must be deleted -- putting an old
    copy back would be wrong.
    """
    if not config:
        return
    if had_config and Path(old_config).exists():
        os.replace(old_config, config)
    elif not had_config and Path(config).exists():
        Path(config).unlink()


def _rollback_savings_json(savings_json, old_savings, had_savings_json):
    """Returns the legacy goals file to its pre-restore state.

    Exactly the same pattern and the same rationale as `_rollback_config`: if
    the file did NOT exist before the restore, a file that appeared during the
    restore MUST BE DELETED -- putting an old copy back would be wrong.
    """
    if had_savings_json and Path(old_savings).exists():
        os.replace(old_savings, savings_json)
    elif not had_savings_json and Path(savings_json).exists():
        Path(savings_json).unlink()


def _quarantine_stale_savings_json(savings_json):
    """Moves the legacy JSON ASIDE after a successful restore -- it does not delete it.

    The restore replaced the database wholesale; the JSON left on disk belongs
    to the previous generation. Leaving it in place would mean the migration
    engine evaluating it at the next startup, leaving the chance of two
    generations mixing open. Deleting it would be destroying data: the file
    stays in the user's data directory as `.stale-<time>` and is never read
    again in normal operation.
    """
    savings_json = Path(savings_json)
    if not savings_json.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = savings_json.with_name(f"{savings_json.name}.stale-{stamp}")
    counter = 1
    while target.exists():
        target = savings_json.with_name(
            f"{savings_json.name}.stale-{stamp}-{counter}"
        )
        counter += 1
    os.replace(savings_json, target)
    return target


def _discard_journal(journal_dir):
    shutil.rmtree(journal_dir, ignore_errors=True)


def recover_interrupted_restore(db_path=DB_NAME, *, key_provider=None,
                                config_path=None):
    """Safely rolls back a half-finished restore at startup.

    Called at application startup. Does nothing if there is no journal. If
    there is one, the restore was interrupted by a process crash and the
    profile may be in a mixed state; the old generation is brought back.

    FAIL-CLOSED: if the journal cannot be read or carries an unrecognised
    state it is not silently ignored, and `DataMigrationError` is raised.
    Looking at a corrupt journal and assuming "everything is fine" is worse
    than starting on a mixed profile.
    """
    journal_dir = _restore_journal_dir(db_path)
    journal_file = journal_dir / _JOURNAL_NAME
    if not journal_file.exists():
        return {"recovered": False, "reason": "no-journal"}

    try:
        payload = json.loads(journal_file.read_text(encoding="utf-8"))
        state = payload["state"]
    except (OSError, ValueError, KeyError) as exc:
        raise DataMigrationError(
            "Yarım restore journal'ı okunamadı; profil elle incelenmeli."
        ) from exc
    if state not in _JOURNAL_STATES:
        raise DataMigrationError(
            f"Tanınmayan restore journal state'i: {state!r}"
        )

    db_path = Path(payload.get("db_path") or db_path)
    config = Path(payload["config_path"]) if payload.get("config_path") else (
        Path(config_path) if config_path else None
    )
    had_config = payload.get("had_config", False)
    had_savings_json = payload.get("had_savings_json", False)
    old_db = journal_dir / "old-finance.db"
    old_config = journal_dir / "old-config.json"
    old_savings = journal_dir / "old-savings_goals.json"
    savings_json = _savings_json_path(db_path)

    if state in _COMMITTED_STATES:


        if not db_path.exists():
            raise DataMigrationError(
                "Restore tamamlanmış görünüyor ama veritabanı bulunamadı; "
                "profil elle incelenmeli."
            )


        _quarantine_stale_savings_json(savings_json)
        _discard_journal(journal_dir)      # idempotent: rmtree(ignore_errors)
        return {
            "recovered": True,
            "state": state,
            "action": "cleanup-only",
            "db_path": str(db_path),
        }


    if old_db.exists():
        if db_path.exists():
            db_path.unlink()
        os.replace(old_db, db_path)
    _rollback_config(config, old_config, had_config)
    _rollback_savings_json(savings_json, old_savings, had_savings_json)
    _discard_journal(journal_dir)
    return {
        "recovered": True,
        "state": state,
        "action": "rolled-back",
        "db_path": str(db_path),
    }


def restore_backup(
    package_path,
    passphrase,
    *,
    db_path=DB_NAME,
    key_path=None,
    key_provider=None,
    config_path=None,
    safety_backup_path=None,
    _failure_hook=None,
):
    """Verify, safety-backup, then replace DB/key with rollback on failure."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    provider = _key_provider(key_path, key_provider)
    config = Path(config_path) if config_path else None
    safety_backup_path = Path(
        safety_backup_path
        or db_path.with_name(
            f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}.helyosfer-backup"
        )
    )
    current_key = provider.load_key()

    with tempfile.TemporaryDirectory(
        prefix="helyosfer-restore-", dir=str(db_path.parent)
    ) as temp_dir:
        temp = Path(temp_dir)


        _stage_package(package_path, temp)
        verification = _verify_staged(temp, passphrase)

        if db_path.exists() and current_key is not None:
            create_backup(
                safety_backup_path,
                passphrase,
                db_path=db_path,
                key_provider=provider,
                config_path=str(config) if config else None,
            )

        staged_db = temp / "finance.db"
        staged_key = temp / "encryption.key"
        staged_key.write_bytes(verification["key"])
        os.chmod(staged_key, 0o600)


        journal_dir = _restore_journal_dir(db_path)
        old_db = journal_dir / "old-finance.db"
        old_config = journal_dir / "old-config.json"
        old_savings = journal_dir / "old-savings_goals.json"
        savings_json = _savings_json_path(db_path)
        try:
            journal_dir.mkdir(mode=0o700, parents=True, exist_ok=True)


            had_config = config is not None and config.exists()
            if config is not None and had_config:
                shutil.copy2(config, old_config)


            had_savings_json = savings_json.exists()
            if had_savings_json:
                shutil.copy2(savings_json, old_savings)
            _write_journal(journal_dir, "STAGED", db_path, config, had_config,
                           had_savings_json)

            if db_path.exists():
                os.replace(db_path, old_db)
            _write_journal(
                journal_dir, "ROLLBACK_GENERATION_READY", db_path, config,
                had_config, had_savings_json,
            )
            if _failure_hook:
                _failure_hook("after_old_files_staged")
            os.replace(staged_db, db_path)
            _write_journal(
                journal_dir, "DB_REPLACED", db_path, config,
                had_config, had_savings_json,
            )
            if _failure_hook:
                _failure_hook("after_database_replaced")
            incoming_key = staged_key.read_bytes()
            if current_key is None:
                provider.store_key(incoming_key)
            else:
                provider.replace_key(
                    incoming_key, expected_current=current_key
                )
            _write_journal(
                journal_dir, "KEY_REPLACED", db_path, config,
                had_config, had_savings_json,
            )
            if _failure_hook:
                _failure_hook("after_key_replaced")
            if config and verification["config"] is not None:
                config.parent.mkdir(parents=True, exist_ok=True)
                config.write_bytes(verification["config"])
            _write_journal(
                journal_dir, "CONFIG_REPLACED", db_path, config,
                had_config, had_savings_json,
            )
            if _failure_hook:
                _failure_hook("after_config_replaced")
            _integrity_check(db_path)
            verify_database_key(db_path, provider.load_key())
            if _failure_hook:
                _failure_hook("after_post_verification")
        except Exception as exc:
            if db_path.exists():
                db_path.unlink()
            if old_db.exists():
                os.replace(old_db, db_path)
            restored_key = provider.load_key()
            if (
                current_key is not None
                and restored_key is not None
                and restored_key != current_key
            ):
                provider.replace_key(
                    current_key, expected_current=restored_key
                )
            elif current_key is None and restored_key is not None:
                provider.delete_key(expected_current=restored_key)


            _rollback_config(config, old_config, had_config)
            _rollback_savings_json(savings_json, old_savings, had_savings_json)
            _discard_journal(journal_dir)
            raise DataMigrationError(
                "Restore başarısız oldu; önceki veriler geri yüklendi."
            ) from exc


        _write_journal(
            journal_dir, "VERIFIED", db_path, config,
            had_config, had_savings_json,
        )
        if _failure_hook:
            _failure_hook("before_committed_marker")
        _write_journal(
            journal_dir, "COMMITTED", db_path, config,
            had_config, had_savings_json,
        )
        if _failure_hook:
            _failure_hook("after_committed_marker")


        stale_savings = _quarantine_stale_savings_json(savings_json)
        if _failure_hook:
            _failure_hook("after_savings_json_quarantined")


        _discard_journal(journal_dir)

    from utils.crypto import _get_aead_key
    _get_aead_key.cache_clear()
    return {
        "restored": True,
        "safety_backup_path": str(safety_backup_path),
        "stale_savings_json": str(stale_savings) if stale_savings else None,
    }
