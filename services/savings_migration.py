"""The migration engine that moves old `savings_goals.json` records into SQLite.

WHY IT EXISTS (contract: docs/ARCHITECTURE.md): savings goals lived in two
places -- the money in SQLite, the card on screen in `savings_goals.json`. The
JSON marked the goal by NUMERIC id alone, and because `sqlite_sequence` lives
inside `finance.db` a restore rewound that counter: a goal created after a
restore took back the id the stale JSON still pointed at, and the user's money
was written to the wrong goal.

This module is COMPLETELY independent of the UI, so it can be tested
directly.

THE CONTRACT -- all of it holds at once:

  * Idempotent. However many times it runs it never produces a row twice; it
    achieves that with a per-record marker (`savings_migration_state`) written
    in THE SAME transaction as the INSERTs.
  * One transaction. `BEGIN IMMEDIATE` ... `COMMIT`. If the commit did not
    happen, nothing changed.
  * It NEVER OVERWRITES an existing SQL row. On a matching record only the
    EMPTY color/created_at/auto_deposit fields are filled; the amounts are
    untouched.
  * It CREATES NO financial value. No account balance and no `balance_events`
    row changes. A JSON record with no counterpart that HOLDS MONEY is NOT
    INSERTED -- it is quarantined (see the note below).
  * It does not decide automatically under ambiguity; it quarantines and
    records the case to be shown to the user.
  * It DOES NOT TOUCH the JSON before successful verification, and does not
    delete it afterwards either -- it preserves it as
    `savings_goals.json.migrated-<ISO>`.
  * The final marker is written only AFTER everything has finished.

"WHY A RECORD WITH NO COUNTERPART THAT CARRIES MONEY IS NOT INSERTED": in the
old application, depositing into a goal went through `deposit_to_goal`, so
every goal with money HAD a row in SQL. A JSON record with no counterpart that
nevertheless claims `current > 0` is therefore an anomaly: the row was deleted
or is left from another generation, and there is no way to know whether the
money was returned to the account. Inserting it would be conjuring money into
the ledger that never left any account (`_backfill_ledger_baseline` would
write it an opening event). The record is quarantined: the data is NOT LOST
and is shown to the user, but it is not turned into money automatically.

"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

from database import db as _db
from database.db import SECRET_KEY
from utils.app_paths import data_dir
from utils.crypto import decrypt, encrypt
from utils.errors import DecryptionError, KeyUnavailableError
from utils.financial_decimal import fiat

SAVINGS_JSON_NAME = "savings_goals.json"


def _default_db_path():
    """Resolves the database path AT CALL TIME.

    `from database.db import DB_NAME` binds at import time, and callers that
    patch `database.db.DB_NAME` (tests, the reset flow) would silently write
    to the REAL profile. The rest of the code base also reads the value on
    every call (see `database/db.py::get_connection`).
    """
    return _db.DB_NAME


MIGRATION_MARKER = "savings_json_to_sql"

_JOURNAL_DIRNAME = ".helysofer-savings-migration"
_JOURNAL_NAME = "journal.json"

STATE_READ = "OKUNDU"
STATE_PLANNED = "PLANLANDI"
STATE_APPLIED = "UYGULANDI"
STATE_VERIFIED = "DOĞRULANDI"
STATE_RETIRED = "EMEKLİ"


DECISION_MATCH = "match"
DECISION_INSERT = "insert"
DECISION_QUARANTINE = "quarantine"

REASON_ID_COLLISION = "ayni-id-farkli-hedef"
REASON_AMBIGUOUS = "ayni-ad-tutar-farkli-id"
REASON_DUPLICATE_ID = "json-icinde-yinelenen-id"
REASON_UNMATCHED_WITH_BALANCE = "karsiligi-yok-uzerinde-para-var"
REASON_INVALID = "okunamayan-kayit"
REASON_STALE_JSON = "restore-sonrasi-bayat-json"
REASON_UNREADABLE_FILE = "bozuk-json-dosyasi"


QUARANTINE_USER_MESSAGES = {
    REASON_ID_COLLISION:
        "Bu hedefin numarası başka bir hedefe ait görünüyor; otomatik "
        "taşımak yanlış hedefe para yazma riski taşıyordu.",
    REASON_AMBIGUOUS:
        "Aynı ad ve tutarda başka bir hedef var; hangisinin kastedildiği "
        "kesin olmadığı için birleştirilmedi.",
    REASON_DUPLICATE_ID:
        "Eski dosyada aynı numarayı taşıyan birden çok hedef var.",
    REASON_UNMATCHED_WITH_BALANCE:
        "Bu hedefin veritabanında karşılığı yok ama üzerinde birikim "
        "görünüyor; para yoktan var edilmesin diye taşınmadı.",
    REASON_INVALID:
        "Eski dosyadaki bu kayıt okunamadı.",
    REASON_STALE_JSON:
        "Bu kayıt, geri yükleme öncesinden kalmış eski bir dosyadan geliyor "
        "ve güncel verinizle çelişebilir.",
    REASON_UNREADABLE_FILE:
        "Eski hedef dosyası okunamadı; hiçbir kayıt taşınmadı ve dosya "
        "olduğu gibi saklandı.",
}


class SavingsMigrationError(Exception):
    """The migration could not complete safely; no persistent decision was made."""


# ── Yollar ────────────────────────────────────────────────────────────────
def savings_json_path(directory=None) -> Path:
    return Path(directory or data_dir()) / SAVINGS_JSON_NAME


def _journal_dir(db_path) -> Path:
    return Path(db_path).parent / _JOURNAL_DIRNAME


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _retire_path(json_path: Path, suffix: str) -> Path:
    """`savings_goals.json` -> `savings_goals.json.<suffix>-<time>`.

    If a second file is produced within the same second (tests and rapid
    successive restores) a counter is appended; `os.replace` would silently
    overwrite.
    """
    base = json_path.with_name(f"{json_path.name}.{suffix}-{_timestamp()}")
    candidate = base
    counter = 1
    while candidate.exists():
        candidate = base.with_name(f"{base.name}-{counter}")
        counter += 1
    return candidate


def _write_journal(db_path, state, detail=None):
    directory = _journal_dir(db_path)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    payload = {
        "state": state,
        "db_path": str(db_path),
        "detail": detail or {},
        "written_at": datetime.now().isoformat(timespec="seconds"),
    }
    target = directory / _JOURNAL_NAME
    handle_fd, staged = tempfile.mkstemp(dir=str(directory), prefix=".journal-")
    with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(staged, target)
    return target


def read_journal(db_path=None):
    path = _journal_dir(db_path or _default_db_path()) / _JOURNAL_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _clear_journal(db_path):
    shutil.rmtree(_journal_dir(db_path), ignore_errors=True)


def _connect(db_path):
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def migration_completed(db_path=None) -> bool:
    """Is the final marker present? (The sole basis for the stale-JSON rule.)"""
    db_path = Path(db_path or _default_db_path())
    if not db_path.exists():
        return False
    with closing(_connect(db_path)) as conn:
        try:
            row = conn.execute(
                "SELECT 1 FROM savings_migration_state WHERE marker = ?",
                (MIGRATION_MARKER,),
            ).fetchone()
        except sqlite3.Error:

            return False
    return row is not None


def pending_quarantine(db_path=None):
    """Quarantine records not YET shown to the user."""
    db_path = Path(db_path or _default_db_path())
    if not db_path.exists():
        return []
    with closing(_connect(db_path)) as conn:
        try:
            rows = conn.execute(
                "SELECT id, reason, source, legacy_id, goal_name,"
                " target_amount, current_amount, quarantined_at"
                " FROM savings_migration_quarantine"
                " WHERE acknowledged = 0 ORDER BY id"
            ).fetchall()
        except sqlite3.Error:
            return []
    return [_readable_quarantine_row(row) for row in rows]


def _readable_quarantine_row(row):
    name = row["goal_name"]
    if name:
        try:
            name = decrypt(name, SECRET_KEY)
        except (DecryptionError, KeyUnavailableError, ValueError, TypeError):
            name = "Bilinmeyen Hedef"
    return {
        "id": row["id"],
        "reason": row["reason"],
        "message": QUARANTINE_USER_MESSAGES.get(row["reason"], ""),
        "source": row["source"],
        "legacy_id": row["legacy_id"],
        "goal_name": name,
        "target_amount": row["target_amount"],
        "current_amount": row["current_amount"],
        "quarantined_at": row["quarantined_at"],
    }


def acknowledge_quarantine(db_path=None):
    """Marks the quarantine notification as shown.

    The notification is ONE-SHOT but the record is NOT DELETED: the user must
    be able to see later which goals could not be migrated.
    """
    db_path = Path(db_path or _default_db_path())
    if not db_path.exists():
        return 0
    with closing(_connect(db_path)) as conn:
        try:
            cursor = conn.execute(
                "UPDATE savings_migration_quarantine SET acknowledged = 1"
                " WHERE acknowledged = 0"
            )
        except sqlite3.Error:
            return 0
        conn.commit()
        return cursor.rowcount


# ── JSON okuma ────────────────────────────────────────────────────────────
def _parse_json_records(json_path: Path):
    """Extracts the goal list from the legacy JSON goal file.

    The format: {"goals": {"data": [ ... ]}}. Parsed with the standard
    library only -- this module has to be able to run without the UI.
    """
    raw = json_path.read_text(encoding="utf-8")
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError("beklenmeyen JSON kökü")
    goals = document.get("goals")
    if goals is None:
        return []
    if not isinstance(goals, dict):
        raise ValueError("beklenmeyen 'goals' bölümü")
    data = goals.get("data", [])
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError("beklenmeyen 'data' bölümü")
    return data


def _record_fingerprint(index, record):
    """The per-record marker key.

    It depends on the content AND the order: if there are two records
    identical to each other, both have to be marked separately, otherwise the
    second would be taken for "already applied" and silently dropped.
    """
    payload = json.dumps(
        [index, record], sort_keys=True, ensure_ascii=False,
        separators=(",", ":"), default=str,
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"record:{digest[:32]}"


def _coerce_record(record):
    """Validates and normalises a raw JSON record; returns None if it cannot."""
    if not isinstance(record, dict):
        return None
    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    try:
        target = float(fiat(record.get("target", 0) or 0))
        current = float(fiat(record.get("current", 0) or 0))
    except (TypeError, ValueError, ArithmeticError):
        return None
    if target <= 0 or current < 0:
        return None
    legacy_id = record.get("id")
    if legacy_id is not None:
        try:
            legacy_id = int(legacy_id)
        except (TypeError, ValueError):
            return None
    color = record.get("color")
    if color is not None and not isinstance(color, str):
        color = None
    created_at = record.get("created_at")
    if created_at is not None and not isinstance(created_at, str):
        created_at = None
    return {
        "legacy_id": legacy_id,
        "name": name.strip(),
        "target": target,
        "current": current,
        "color": color,
        "auto_deposit": bool(record.get("auto_deposit", False)),
        "created_at": created_at,
    }


def _existing_goals(conn):
    rows = conn.execute(
        "SELECT id, goal_uid, goal_name, target_amount, current_amount,"
        " color, auto_deposit, created_at FROM savings_goals"
    ).fetchall()
    goals = []
    for row in rows:
        goals.append({
            "id": row["id"],
            "goal_uid": row["goal_uid"],
            "name": decrypt(row["goal_name"], SECRET_KEY),
            "target": float(row["target_amount"] or 0.0),
            "current": float(row["current_amount"] or 0.0),
            "color": row["color"],
            "auto_deposit": row["auto_deposit"],
            "created_at": row["created_at"],
        })
    return goals


def classify(records, existing):
    """Binds every JSON record to a decision. A PURE function -- no I/O.

    Keeping it separate and pure is deliberate: the decision table (plan §6)
    is the riskiest logic in this code base, and a wrong decision writes the
    user's money to the wrong goal. Because it is pure it can be tested
    directly, without a database.
    """
    by_id = {goal["id"]: goal for goal in existing if goal["id"] is not None}
    name_amount_index: dict[tuple[str, float], list[dict]] = {}
    for goal in existing:
        name_amount_index.setdefault((goal["name"], round(goal["target"], 2)), []).append(goal)

    duplicated_ids = set()
    seen_ids = set()
    for record in records:
        legacy_id = record["legacy_id"]
        if legacy_id is None:
            continue
        if legacy_id in seen_ids:
            duplicated_ids.add(legacy_id)
        seen_ids.add(legacy_id)


    decisions: list[tuple[str, dict, object]] = []
    for record in records:
        legacy_id = record["legacy_id"]
        key = (record["name"], round(record["target"], 2))

        if legacy_id is not None and legacy_id in duplicated_ids:
            decisions.append((DECISION_QUARANTINE, record, REASON_DUPLICATE_ID))
            continue

        candidate = by_id.get(legacy_id) if legacy_id is not None else None
        if candidate is not None:
            if candidate["name"] == record["name"]:

                decisions.append((DECISION_MATCH, record, candidate))
            else:

                decisions.append(
                    (DECISION_QUARANTINE, record, REASON_ID_COLLISION))
            continue

        if name_amount_index.get(key):


            decisions.append((DECISION_QUARANTINE, record, REASON_AMBIGUOUS))
            continue

        if record["current"] > 0:


            decisions.append(
                (DECISION_QUARANTINE, record, REASON_UNMATCHED_WITH_BALANCE))
            continue

        decisions.append((DECISION_INSERT, record, None))
    return decisions


# ── Uygulama ──────────────────────────────────────────────────────────────
def _applied_markers(conn):
    rows = conn.execute(
        "SELECT marker FROM savings_migration_state WHERE marker LIKE 'record:%'"
    ).fetchall()
    return {row["marker"] for row in rows}


def _quarantine(conn, reason, source, record, raw):
    conn.execute(
        "INSERT INTO savings_migration_quarantine"
        " (quarantined_at, reason, source, legacy_id, goal_name,"
        "  target_amount, current_amount, payload, acknowledged)"
        " VALUES (?,?,?,?,?,?,?,?,0)",
        (
            datetime.now().isoformat(timespec="seconds"),
            reason,
            source,
            record.get("legacy_id") if record else None,
            encrypt(str(record["name"]), SECRET_KEY) if record else None,
            record.get("target") if record else None,
            record.get("current") if record else None,
            encrypt(
                json.dumps(raw, ensure_ascii=False, default=str), SECRET_KEY
            ),
        ),
    )


def _insert_goal(conn, record, taken_ids):
    """Writes the new goal. The old numeric id is PRESERVED where possible.

    Preserving the old id does two things: (1) the identity mapping in the
    user's own file is not broken, (2) the `AUTOINCREMENT` counter moves ABOVE
    that value, so the same id is never handed out again.
    """
    goal_uid = str(uuid.uuid4())
    columns = (
        "goal_name, target_amount, current_amount, target_date, status,"
        " goal_uid, color, auto_deposit, created_at"
    )
    values = (
        encrypt(record["name"], SECRET_KEY),
        record["target"],
        record["current"],
        None,
        "tamamlandi" if fiat(record["current"]) >= fiat(record["target"])
        else "aktif",
        goal_uid,
        record["color"],
        1 if record["auto_deposit"] else 0,
        record["created_at"],
    )
    legacy_id = record["legacy_id"]
    if legacy_id is not None and legacy_id not in taken_ids:
        conn.execute(
            f"INSERT INTO savings_goals (id, {columns})"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (legacy_id, *values),
        )
        taken_ids.add(legacy_id)
    else:
        conn.execute(
            f"INSERT INTO savings_goals ({columns})"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            values,
        )
    return goal_uid


def _complete_fields(conn, record, existing_goal):
    """Fills ONLY the empty fields of the matching row.

    It DOES NOT TOUCH the amounts or the name. `auto_deposit` can change only
    in the 0 -> 1 direction: a preference the user turned on must not be
    turned off by an old file.
    """
    updates = []
    params = []
    if not existing_goal["color"] and record["color"]:
        updates.append("color = ?")
        params.append(record["color"])
    if not existing_goal["created_at"] and record["created_at"]:
        updates.append("created_at = ?")
        params.append(record["created_at"])
    if record["auto_deposit"] and not existing_goal["auto_deposit"]:
        updates.append("auto_deposit = 1")
    if not updates:
        return False
    params.append(existing_goal["id"])
    conn.execute(
        f"UPDATE savings_goals SET {', '.join(updates)} WHERE id = ?",  # nosec B608
        params,
    )
    return True


def _financial_fingerprint(conn):
    """A digest of everything the migration MUST NOT CHANGE."""
    accounts = conn.execute(
        "SELECT COALESCE(SUM(balance), 0) FROM accounts"
    ).fetchone()[0]
    events = conn.execute("SELECT COUNT(*) FROM balance_events").fetchone()[0]
    event_sum = conn.execute(
        "SELECT COALESCE(SUM(delta), 0) FROM balance_events"
    ).fetchone()[0]
    existing_total = conn.execute(
        "SELECT COALESCE(SUM(current_amount), 0) FROM savings_goals"
    ).fetchone()[0]
    return {
        "accounts_total": round(float(accounts or 0.0), 2),
        "balance_events": int(events),
        "balance_events_delta": round(float(event_sum or 0.0), 2),
        "savings_total": round(float(existing_total or 0.0), 2),
    }


def _safety_snapshot(db_path: Path) -> Path:
    """A byte-for-byte copy of the database from BEFORE the migration.

    The password-protected `create_backup` is NOT USED -- that asks for a
    recovery password, and this migration runs at startup without asking the
    user anything. The copy is taken with SQLite's own online-backup API
    (copying the file could produce an inconsistent copy while a WAL is open)
    and does NOT CONTAIN the encryption key: its content is identical to the
    live database, in the same directory and under the same protection.
    """
    target = db_path.with_name(
        f"{db_path.name}.pre-savings-migration-{_timestamp()}"
    )
    counter = 1
    while target.exists():
        target = db_path.with_name(f"{target.name}-{counter}")
        counter += 1
    with closing(sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(str(target))) as destination:
            source.backup(destination)
    try:
        os.chmod(target, 0o600)
    except OSError:


        pass
    return target


def _outcome(status, **extra):
    result = {
        "status": status,
        "inserted": 0,
        "completed": 0,
        "quarantined": 0,
        "skipped": 0,
    }
    result.update(extra)
    return result


def run_savings_migration(*, json_path=None, db_path=None, _failure_hook=None):
    """Moves the JSON goals into SQLite, under the contract in the module docstring.

    `_failure_hook` is for tests to inject an interruption at each critical
    stage; in production it is `None` (the same pattern as `_failure_hook` in
    restore).
    """
    db_path = Path(db_path or _default_db_path())
    json_path = Path(json_path) if json_path else savings_json_path(db_path.parent)

    if not db_path.exists():

        return _outcome("no-database")


    journal = read_journal(db_path)
    if (
        journal
        and journal.get("state") in (STATE_APPLIED, STATE_VERIFIED, STATE_RETIRED)
        and not json_path.exists()
        and not migration_completed(db_path)
    ):
        return _retire(db_path, json_path, _outcome("resumed"), _failure_hook)

    if not json_path.exists():
        return _outcome("no-json")


    if migration_completed(db_path):
        return _quarantine_stale_json(json_path, db_path, _failure_hook)

    try:
        raw_records = _parse_json_records(json_path)
    except (OSError, UnicodeError, ValueError):
        return _quarantine_unreadable_json(json_path, db_path, _failure_hook)

    _write_journal(db_path, STATE_READ, {"records": len(raw_records)})

    records = []
    invalid = []
    for index, raw in enumerate(raw_records):
        coerced = _coerce_record(raw)
        if coerced is None:
            invalid.append((index, raw))
        else:
            records.append((index, coerced, raw))

    if not records and not invalid:


        return _retire(db_path, json_path, _outcome("empty"), _failure_hook)

    try:


        encrypt("anahtar-denemesi", SECRET_KEY)
        with closing(_connect(db_path)) as conn:
            existing = _existing_goals(conn)
            before = _financial_fingerprint(conn)
            applied = _applied_markers(conn)
            taken_ids = {goal["id"] for goal in existing}
    except KeyUnavailableError:


        _write_journal(db_path, STATE_READ, {"aborted": "key-unavailable"})
        return _outcome("key-unavailable")
    except (DecryptionError, ValueError, TypeError) as exc:
        raise SavingsMigrationError(
            "Mevcut hedef adları çözülemedi; göç durduruldu."
        ) from exc

    decisions = classify([record for _, record, _ in records], existing)
    plan = [
        (index, record, raw, decision, payload)
        for (index, record, raw), (decision, _, payload)
        in zip(records, decisions)
    ]
    _write_journal(db_path, STATE_PLANNED, {
        "insert": sum(1 for item in plan if item[3] == DECISION_INSERT),
        "match": sum(1 for item in plan if item[3] == DECISION_MATCH),
        "quarantine": sum(1 for item in plan if item[3] == DECISION_QUARANTINE)
        + len(invalid),
    })

    snapshot = _safety_snapshot(db_path)
    if _failure_hook:
        _failure_hook("after_safety_snapshot")

    result = _outcome("migrated", safety_snapshot=str(snapshot))
    conn = _connect(db_path)


    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        for index, raw in invalid:
            marker = _record_fingerprint(index, raw)
            if marker in applied:
                result["skipped"] += 1
                continue
            _quarantine(conn, REASON_INVALID, "legacy-json", None, raw)
            _mark_record(conn, marker, REASON_INVALID)
            result["quarantined"] += 1

        if _failure_hook:
            _failure_hook("after_invalid_records")

        for index, record, raw, decision, payload in plan:
            marker = _record_fingerprint(index, raw)
            if marker in applied:
                result["skipped"] += 1
                continue
            if decision == DECISION_INSERT:
                _insert_goal(conn, record, taken_ids)
                result["inserted"] += 1
                _mark_record(conn, marker, DECISION_INSERT)
            elif decision == DECISION_MATCH:
                if _complete_fields(conn, record, payload):
                    result["completed"] += 1
                _mark_record(conn, marker, DECISION_MATCH)
            else:
                _quarantine(conn, payload, "legacy-json", record, raw)
                result["quarantined"] += 1
                _mark_record(conn, marker, payload)

        if _failure_hook:
            _failure_hook("before_commit")
        conn.commit()
        committed = True
    finally:
        if not committed:
            conn.rollback()
        conn.close()

    _write_journal(db_path, STATE_APPLIED, result)
    if _failure_hook:
        _failure_hook("after_commit")

    _verify(db_path, before, result)
    _write_journal(db_path, STATE_VERIFIED, result)
    if _failure_hook:
        _failure_hook("after_verification")

    return _retire(db_path, json_path, result, _failure_hook)


def _mark_record(conn, marker, detail):
    """The per-record "applied" marker -- in THE SAME transaction as the INSERTs.

    Without this row, a process dying between the commit and the retirement
    would migrate THE SAME records a second time at the next startup.
    """
    conn.execute(
        "INSERT OR IGNORE INTO savings_migration_state"
        " (marker, completed_at, detail) VALUES (?,?,?)",
        (marker, datetime.now().isoformat(timespec="seconds"), str(detail)),
    )


def _verify(db_path, before, result):
    """Measures the things the migration MUST NOT have changed."""
    with closing(_connect(db_path)) as conn:
        after = _financial_fingerprint(conn)
        missing_uid = conn.execute(
            "SELECT COUNT(*) FROM savings_goals WHERE goal_uid IS NULL"
        ).fetchone()[0]

    if after["accounts_total"] != before["accounts_total"]:
        raise SavingsMigrationError("Göç hesap bakiyelerini değiştirdi.")
    if after["balance_events"] != before["balance_events"]:
        raise SavingsMigrationError("Göç defter satırı yazdı.")
    if after["balance_events_delta"] != before["balance_events_delta"]:
        raise SavingsMigrationError("Göç defter toplamını değiştirdi.")
    if after["savings_total"] != before["savings_total"]:


        raise SavingsMigrationError("Göç birikim toplamını değiştirdi.")
    if missing_uid:
        raise SavingsMigrationError("Göç sonrası kimliksiz hedef kaldı.")


def _retire(db_path, json_path, result, _failure_hook=None):
    """Retires the JSON and writes the final marker. THE ORDER MATTERS.

    The file is moved FIRST and the marker written AFTERWARDS. In the reverse
    order, a process dying between the two steps would be left with a marker
    saying "migration complete" and a JSON still sitting in place; the next
    startup would take that file for STALE, quarantine it, and show the user a
    needless warning.
    """
    retired = None
    if json_path.exists():
        retired = _retire_path(json_path, "migrated")
        os.replace(json_path, retired)
        result["retired_path"] = str(retired)
    if _failure_hook:
        _failure_hook("after_json_retired")

    with closing(_connect(db_path)) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO savings_migration_state"
            " (marker, completed_at, detail) VALUES (?,?,?)",
            (
                MIGRATION_MARKER,
                datetime.now().isoformat(timespec="seconds"),
                json.dumps(
                    {
                        "inserted": result["inserted"],
                        "completed": result["completed"],
                        "quarantined": result["quarantined"],
                        "retired_path": str(retired) if retired else None,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        conn.commit()
    _write_journal(db_path, STATE_RETIRED, {"retired_path": str(retired)})
    if _failure_hook:
        _failure_hook("after_marker_written")
    _clear_journal(db_path)
    return result


def _quarantine_stale_json(json_path: Path, db_path: Path, _failure_hook=None):
    """JSON left behind after a restore: NO migration, but quarantine YES."""
    try:
        raw_records = _parse_json_records(json_path)
    except (OSError, UnicodeError, ValueError):
        raw_records = []

    result = _outcome("stale-json")
    with closing(_connect(db_path)) as conn:
        for raw in raw_records:
            record = _coerce_record(raw)
            _quarantine(conn, REASON_STALE_JSON, "stale-json", record, raw)
            result["quarantined"] += 1
        conn.commit()
    if _failure_hook:
        _failure_hook("after_stale_quarantine_rows")

    retired = _retire_path(json_path, "stale")
    os.replace(json_path, retired)
    result["retired_path"] = str(retired)
    _write_journal(db_path, STATE_RETIRED, {"stale_path": str(retired)})
    _clear_journal(db_path)
    return result


def _quarantine_unreadable_json(json_path: Path, db_path: Path,
                                _failure_hook=None):
    """Corrupt or partial JSON: NO PARTIAL MIGRATION.

    The file's content is NOT COPIED into the quarantine row -- because it
    cannot be read it cannot be turned into a meaningful record, and moving raw
    data of unknown nature into the database would be a new problem. The file
    itself is kept as it is, as `.unreadable-<time>`; the quarantine row points
    at it.
    """
    detail: dict[str, object] = {"file": json_path.name}
    try:
        detail["bytes"] = json_path.stat().st_size
    except OSError:
        detail["bytes"] = None

    retired = _retire_path(json_path, "unreadable")
    os.replace(json_path, retired)
    detail["stored_as"] = retired.name
    if _failure_hook:
        _failure_hook("after_unreadable_moved")

    with closing(_connect(db_path)) as conn:
        _quarantine(conn, REASON_UNREADABLE_FILE, "legacy-json", None, detail)
        conn.commit()
    result = _outcome("unreadable-json", quarantined=1,
                      retired_path=str(retired))
    _write_journal(db_path, STATE_RETIRED, detail)
    _clear_journal(db_path)
    return result
