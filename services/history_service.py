"""Time machine: reconstructs the balance at a past date from the ledger.

HOW IT WORKS
------------
Two sources are used together:

  * `daily_balance_snapshot` -- a total written once a day (a fast start),
  * `balance_events`         -- the signed record of every balance change.

`get_balance_at(date)` finds the NEAREST snapshot at or before the requested
date, then replays only the events between that snapshot and the target date.
If there is no snapshot it replays from the start of the ledger. The cost
therefore stays proportional to the number of events accumulated since the
last snapshot, not to how far back in time you go.

WHY THERE IS NO DECRYPTION
--------------------------
Unlike insights_service, no decryption is needed here: `balance_events.delta`
and `accounts.balance` are plain REAL. That is exactly why the ledger is kept
in the clear -- if the replay had to decrypt every row with AES it would be
unusable over long histories (see the balance_events schema note in
init_db.py).

THE SIGN CONVENTION
-------------------
The delta of `entity_type='account'` events applies directly to the total
balance. `entity_type='savings_goal'` events do NOT apply to the total: a
transfer into a goal already produces an outgoing event on the account side,
and adding both would count the money twice. Goal events are tracked
separately under `savings_total`.

"""

import json
import sqlite3
from datetime import datetime

from database.db import get_connection

ACCOUNT = "account"
SAVINGS_GOAL = "savings_goal"


def _normalize_date(value):
    """Reduces a date/datetime/str input to the 'YYYY-MM-DD' form."""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def _day_end(date_str):
    """The end-of-day boundary: so that ALL of that day's events are included.

    Because `ts` is stored in the 'YYYY-MM-DD HH:MM:SS' form, a plain string
    comparison is identical to chronological order; '<= date 23:59:59' means
    covering that day completely.
    """
    return f"{date_str} 23:59:59"


def _compute_current_totals(cursor):
    """The current account total and the account/goal breakdown."""
    cursor.execute("SELECT id, balance FROM accounts")
    accounts = {str(r["id"]): (r["balance"] or 0.0) for r in cursor.fetchall()}
    try:
        cursor.execute("SELECT id, current_amount FROM savings_goals")
        goals = {str(r["id"]): (r["current_amount"] or 0.0) for r in cursor.fetchall()}
    except sqlite3.Error:


        goals = {}
    return sum(accounts.values()), accounts, goals


def write_daily_snapshot(force=False):
    """Writes a snapshot for today; does not write a second one the same day.

    Because `snapshot_date` is UNIQUE, a repeat write would be rejected
    anyway; we still check explicitly so that a deliberate update is possible
    with `force=True` (for a caller wanting to refresh the snapshot during the
    day).

    Returns: the snapshot dict if written, None if one already exists for that
    day.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM daily_balance_snapshot WHERE snapshot_date = ?", (today,)
        )
        existing = cursor.fetchone()
        if existing and not force:
            return None

        total, accounts, goals = _compute_current_totals(cursor)
        breakdown = json.dumps(
            {"accounts": accounts, "savings_goals": goals}, ensure_ascii=False
        )

        if existing:
            cursor.execute(
                "UPDATE daily_balance_snapshot SET total_balance = ?, breakdown_json = ?"
                " WHERE snapshot_date = ?",
                (total, breakdown, today),
            )
        else:
            cursor.execute(
                "INSERT INTO daily_balance_snapshot (snapshot_date, total_balance, breakdown_json)"
                " VALUES (?, ?, ?)",
                (today, total, breakdown),
            )
        conn.commit()
        return {"snapshot_date": today, "total_balance": total,
                "breakdown": {"accounts": accounts, "savings_goals": goals}}
    finally:
        conn.close()


def ledger_start_date(cursor=None):
    """The date of the oldest event in the ledger ('YYYY-MM-DD'), or None if
    the ledger is empty.

    Queries earlier than this date cannot be answered: before the ledger existed the
    application recorded no balance movement, so for that period we HAVE no
    data. Returning zero would mean "you had no money at all" -- which would be
    wrong.
    """


    if cursor is None:
        conn = get_connection()
        try:
            return _ledger_start_date(conn.cursor())
        finally:
            conn.close()
    return _ledger_start_date(cursor)


def _ledger_start_date(cursor):
    """The query itself -- independent of connection ownership."""
    cursor.execute("SELECT MIN(ts) AS first_ts FROM balance_events")
    row = cursor.fetchone()
    first = row["first_ts"] if row else None
    return first[:10] if first else None


def _latest_snapshot_on_or_before(cursor, date_str):
    cursor.execute(
        "SELECT snapshot_date, total_balance, breakdown_json"
        " FROM daily_balance_snapshot WHERE snapshot_date <= ?"
        " ORDER BY snapshot_date DESC LIMIT 1",
        (date_str,),
    )
    row = cursor.fetchone()
    if not row:
        return None
    try:
        breakdown = json.loads(row["breakdown_json"]) if row["breakdown_json"] else {}
    except (json.JSONDecodeError, TypeError):
        breakdown = {}
    return {
        "snapshot_date": row["snapshot_date"],
        "total_balance": row["total_balance"] or 0.0,
        "breakdown": breakdown,
    }


def get_balance_at(date):
    """Returns the balance at the END of the given date.

    Returns:
        {
          "date": "YYYY-MM-DD",
          "total_balance": float,     # the sum of the accounts
          "savings_total": float,     # the total held in savings goals
          "basis": "snapshot" | "replay",
          "snapshot_date": str | None,
          "events_replayed": int,
        }
    """
    date_str = _normalize_date(date)
    boundary = _day_end(date_str)

    conn = get_connection()
    try:
        cursor = conn.cursor()


        start = ledger_start_date(cursor)
        if start is not None and date_str < start:
            return {
                "date": date_str,
                "total_balance": None,
                "savings_total": None,
                "basis": "before_ledger",
                "snapshot_date": None,
                "events_replayed": 0,
                "ledger_start": start,
            }

        snapshot = _latest_snapshot_on_or_before(cursor, date_str)

        if snapshot:
            total = snapshot["total_balance"]
            savings = sum(
                float(v) for v in (snapshot["breakdown"].get("savings_goals") or {}).values()
            )


            lower = _day_end(snapshot["snapshot_date"])
            basis = "snapshot"
        else:
            total = 0.0
            savings = 0.0
            lower = ""
            basis = "replay"

        cursor.execute(
            "SELECT entity_type, delta FROM balance_events"
            " WHERE ts > ? AND ts <= ? ORDER BY ts ASC, id ASC",
            (lower, boundary),
        )
        rows = cursor.fetchall()
        for r in rows:
            if r["entity_type"] == ACCOUNT:
                total += r["delta"] or 0.0
            elif r["entity_type"] == SAVINGS_GOAL:
                savings += r["delta"] or 0.0

        return {
            "date": date_str,
            "total_balance": round(total, 2),
            "savings_total": round(savings, 2),
            "basis": basis,
            "snapshot_date": snapshot["snapshot_date"] if snapshot else None,
            "events_replayed": len(rows),
            "ledger_start": start,
        }
    finally:
        conn.close()


def diff_between(date_a, date_b):
    """Summarises the change between two dates and the events that produced it.

    `date_a` is exclusive (from the end of that day) and `date_b` is inclusive
    -- the natural reading of "what happened from a to b".

    Returns:
        {
          "from", "to",
          "balance_from", "balance_to", "balance_change",
          "savings_from", "savings_to", "savings_change",
          "by_source": {source: {"delta": float, "count": int}},
          "event_count": int,
        }
    """
    a = _normalize_date(date_a)
    b = _normalize_date(date_b)
    if a > b:
        a, b = b, a

    start = get_balance_at(a)
    end = get_balance_at(b)


    truncated = start["basis"] == "before_ledger"

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT source, entity_type, delta FROM balance_events"
            " WHERE ts > ? AND ts <= ? ORDER BY ts ASC, id ASC",
            (_day_end(a), _day_end(b)),
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    by_source: dict[str, dict[str, float]] = {}
    for r in rows:


        if r["entity_type"] != ACCOUNT:
            continue
        key = r["source"] or "bilinmiyor"
        bucket = by_source.setdefault(key, {"delta": 0.0, "count": 0})
        bucket["delta"] += r["delta"] or 0.0
        bucket["count"] += 1
    for bucket in by_source.values():
        bucket["delta"] = round(bucket["delta"], 2)

    return {
        "from": a,
        "to": b,
        "balance_from": start["total_balance"],
        "balance_to": end["total_balance"],
        "balance_change": (
            None if truncated
            else round(end["total_balance"] - start["total_balance"], 2)
        ),
        "savings_from": start["savings_total"],
        "savings_to": end["savings_total"],
        "savings_change": (
            None if truncated
            else round(end["savings_total"] - start["savings_total"], 2)
        ),
        "by_source": by_source,
        "event_count": len(rows),


        "truncated": truncated,
        "ledger_start": end.get("ledger_start"),
    }


