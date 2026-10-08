"""Insight engine: subscription radar, anomaly detection, financial health score.

THE ENCRYPTION CONSTRAINT (the rule that determines the whole shape of this file)
--------------------------------------------------------------------------------
`transactions.amount` and `transactions.description` are stored as
AES-256-CBC-encrypted TEXT (see utils/crypto.py). Statistics therefore CANNOT
be derived on the SQL side with SUM/AVG/window functions -- the sum of
encrypted text is meaningless. We follow the same pattern as
the dashboard metrics and the financial-advice text:

    fetch the rows  ->  decrypt in Python  ->  compute in Python

`category`, `type` and `transaction_date` are kept PLAIN, which is why date
range and category filtering can be (and is) done in SQL -- only the numeric
aggregation moves to Python.

The service is independent of the UI: no function touches a widget and all of
them return plain dicts. Wiring it to the interface is the view layer's job.

"""

import json
import sqlite3
from typing import Any
import statistics
from datetime import datetime, timedelta

from database.db import COMPLETED_TX, get_connection, managed_connection, SECRET_KEY
from utils.crypto import decrypt


AMOUNT_TOLERANCE = 0.10          # %10

MIN_OCCURRENCES = 3


MAX_INTERVAL_CV = 0.35

_FREQUENCY_BUCKETS = [
    ("weekly", 7, 3),
    ("biweekly", 14, 4),
    ("monthly", 30, 8),
    ("quarterly", 90, 15),
    ("yearly", 365, 40),
]


_EXPENSE_TYPES = ("expense", "Gider")
_INCOME_TYPES = ("income", "Gelir")


def _safe_decrypt_float(value, record_id=None):
    """Decode an amount or invalidate the complete insight result."""
    from services.financial_summary_service import decrypt_decimal

    return float(decrypt_decimal(
        value, table="transactions", record_id=record_id
    ))


def _safe_decrypt_text(value, record_id=None, table="transactions"):
    """Decode text or identify the exact unreadable contributing record."""
    from utils.errors import (
        DecryptionError,
        FinancialDataIntegrityError,
        KeyUnavailableError,
    )

    try:
        return decrypt(str(value), SECRET_KEY) or ""
    except KeyUnavailableError:
        raise
    except (DecryptionError, ValueError, TypeError) as exc:
        raise FinancialDataIntegrityError(
            table, record_id, "description", reason=exc
        ) from exc


def _parse_date(raw):
    """Converts `transaction_date` text into a date; None if unrecognised.

    Records can be in either the "%Y-%m-%d %H:%M:%S" or the bare "%Y-%m-%d"
    form (mock data and the CSV migration produce the latter).
    """
    if not raw:
        return None
    text = str(raw).strip()
    for fmt, width in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            return datetime.strptime(text[:width], fmt).date()
        except ValueError:
            continue
    return None


def normalize_name(text):
    """Reduces a description to a comparable name.

    So that "NETFLIX.COM 12/2026", "Netflix   Abonelik" and "netflix" fall to
    the same candidate: lowercased, punctuation -> space, digits and frequent
    suffixes dropped.
    """
    if not text:
        return ""
    lowered = str(text).lower()
    cleaned = "".join(ch if ch.isalnum() else " " for ch in lowered)
    tokens = [t for t in cleaned.split() if t and not t.isdigit() and len(t) > 2]


    tokens = [t for t in tokens if t not in ("otomatik", "odeme", "ödeme")]
    return " ".join(tokens[:3])


def candidate_key(category, name):
    """A stable key for a candidate -- the dismissal table stores this.

    The category plain, the name normalised: once the user has rejected
    "Netflix" it must not be suggested again even if the amount changes.
    """
    return f"{(category or '').strip().lower()}|{normalize_name(name)}"


def _load_transactions(lookback_days, types, decrypt_description=True):
    """Fetches the transactions and decrypts the amount/description in Python.

    The date and type filters are in SQL (those columns are plain), the
    aggregation in Python.

    With `decrypt_description=False` the description column is NOT DECRYPTED
    and stays `None`. WHY (measured, 10K transactions): decrypting the
    description is about half this function's cost (687 ms -> 369 ms, 1.9x).
    The score and forecast paths use only the amount and the date; for them
    the AES work was entirely wasted. The subscription radar and anomaly
    detection NEED the description (they derive the candidate from it), so the
    default is `True` -- they must not silently see an empty description.
    """
    with managed_connection() as conn:
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in types)


        cursor.execute(
            f"""
            SELECT id, amount, type, category, description, transaction_date
            FROM transactions
            WHERE type IN ({placeholders})
              AND date(transaction_date) >= date('now', ?, 'localtime')
              AND {COMPLETED_TX}
            ORDER BY transaction_date ASC
            """,
            (*types, f"-{int(lookback_days)} days"),
        )
        rows = cursor.fetchall()

    records = []
    for r in rows:
        parsed = _parse_date(r["transaction_date"])
        if parsed is None:
            continue
        records.append({
            "id": r["id"],
            "amount": _safe_decrypt_float(r["amount"], r["id"]),
            "type": r["type"],
            "category": r["category"] or "Diğer",
            "description": (
                _safe_decrypt_text(r["description"], r["id"])
                if decrypt_description else None
            ),
            "date": parsed,
        })
    return records


def _dismissed_keys():
    """The keys of the candidates the user has marked 'this is not a subscription'."""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT candidate_key FROM recurring_candidate_dismissals")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.Error:


        return set()
    finally:
        conn.close()


def _tracked_names():
    """The normalised names of the active recurring_payments records.

    The same logic as database.db::has_active_recurring_payment -- because the
    names are encrypted they cannot be searched with a SQL WHERE, so the
    active records are decrypted and compared in Python. The difference: a
    normalised name is used instead of exact equality, because the candidate
    name is derived from a transaction description ("NETFLIX.COM 12/26" versus
    "Netflix").

    Called ONCE per scan, not per candidate: every call decrypts the name of
    every active subscription, and repeating that once per candidate would be
    needless AES work.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT id, name FROM recurring_payments WHERE is_active = 1"
        )
        rows = cursor.fetchall()
    except sqlite3.Error:


        raise
    finally:
        conn.close()

    names = {
        normalize_name(
            _safe_decrypt_text(
                r["name"],
                r["id"],
                "recurring_payments",
            )
        )
        for r in rows
    }
    return {n for n in names if n}


def _matches_tracked(name, tracked):
    """Does the candidate name collide with one of the tracked names?"""
    target = normalize_name(name)
    if not target:
        return False
    return any(
        existing == target or existing in target or target in existing
        for existing in tracked
    )


def _classify_frequency(mean_interval):
    """Converts an average day interval into a human-readable frequency."""
    for label, expected, tolerance in _FREQUENCY_BUCKETS:
        if abs(mean_interval - expected) <= tolerance:
            return label
    return "irregular"


def detect_recurring_candidates(lookback_days=180):
    """Finds recurring expense patterns that have not been added manually.

    The conditions for being a candidate (all of them together):
      * seen at least MIN_OCCURRENCES times with the same category and a
        similar description,
      * the amounts within %AMOUNT_TOLERANCE of each other,
      * the intervals between sightings regular (coefficient of variation
        <= MAX_INTERVAL_CV),
      * NOT already active in recurring_payments,
      * not dismissed by the user.

    Returns: [{name, category, average_amount, frequency, occurrences,
               last_seen, average_interval_days, monthly_cost, key}, ...]
    ordered from most to least expensive.
    """
    records = _load_transactions(lookback_days, _EXPENSE_TYPES)


    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for rec in records:
        if rec["amount"] <= 0:
            continue
        name = normalize_name(rec["description"])
        if not name:
            continue
        groups.setdefault((rec["category"], name), []).append(rec)

    dismissed = _dismissed_keys()
    tracked = _tracked_names()
    candidates = []

    for (category, name), items in groups.items():
        if len(items) < MIN_OCCURRENCES:
            continue

        amounts = [i["amount"] for i in items]
        mean_amount = statistics.fmean(amounts)
        if mean_amount <= 0:
            continue


        if max(abs(a - mean_amount) for a in amounts) > mean_amount * AMOUNT_TOLERANCE:
            continue

        dates = sorted(i["date"] for i in items)
        intervals = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        intervals = [d for d in intervals if d > 0]
        if len(intervals) < MIN_OCCURRENCES - 1:
            continue

        mean_interval = statistics.fmean(intervals)
        if mean_interval <= 0:
            continue

        spread = statistics.pstdev(intervals) if len(intervals) > 1 else 0.0
        if spread / mean_interval > MAX_INTERVAL_CV:
            continue

        frequency = _classify_frequency(mean_interval)
        if frequency == "irregular":
            continue

        key = candidate_key(category, name)
        if key in dismissed:
            continue
        if _matches_tracked(name, tracked):
            continue

        candidates.append({
            "key": key,
            "name": name.title(),
            "category": category,
            "average_amount": round(mean_amount, 2),
            "frequency": frequency,
            "occurrences": len(items),
            "last_seen": dates[-1].isoformat(),
            "average_interval_days": round(mean_interval, 1),


            "monthly_cost": round(mean_amount * (30.0 / mean_interval), 2),

            "next_due_date": (
                dates[-1] + timedelta(days=int(round(mean_interval)))
            ).isoformat(),


            "can_track": frequency in {
                "weekly", "biweekly", "monthly", "quarterly", "yearly",
            },
        })

    candidates.sort(key=lambda c: c["monthly_cost"], reverse=True)
    return candidates


def dismiss_recurring_candidate(key):
    """Permanently dismisses a candidate (the radar never suggests it again)."""
    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO recurring_candidate_dismissals (candidate_key, dismissed_at) VALUES (?, ?)",
            (key, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()


# ── 2. Anomaly detection ───────────────────────────────────────────────────

def _dismissed_anomaly_ids():
    """The transaction ids the user has marked as seen/hidden."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT transaction_id FROM anomaly_dismissals")
        return {row["transaction_id"] for row in cursor.fetchall()}
    finally:
        conn.close()


def dismiss_anomaly(transaction_id):
    """Permanently hides an anomaly's source transaction (idempotent)."""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO anomaly_dismissals "
            "(transaction_id, dismissed_at) VALUES (?, ?)",
            (int(transaction_id), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
    finally:
        conn.close()


def detect_anomalies(lookback_days=90, z_threshold=2.0):
    """Flags unusually large spends per category.

    The mean and standard deviation are computed in Python for each category;
    transactions whose z-score exceeds the threshold count as anomalies. Only
    deviations UPWARD are flagged -- a cheaper-than-normal supermarket run is
    not a warning.

    Categories with fewer than 3 transactions are skipped: deriving a
    deviation from two points is statistically meaningless and would be noise
    for the user.

    Returns: [{id, category, amount, date, description, z_score, mean, deviation}]
    ordered by descending z_score.
    """
    records = _load_transactions(lookback_days, _EXPENSE_TYPES)
    dismissed_ids = _dismissed_anomaly_ids()

    by_category: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        if rec["amount"] > 0:
            by_category.setdefault(rec["category"], []).append(rec)

    anomalies = []
    for category, items in by_category.items():
        if len(items) < 3:
            continue
        amounts = [i["amount"] for i in items]
        mean = statistics.fmean(amounts)
        stdev = statistics.pstdev(amounts)
        if stdev <= 0:

            continue
        for rec in items:
            if rec["id"] in dismissed_ids:
                continue
            z = (rec["amount"] - mean) / stdev
            if z >= z_threshold:
                anomalies.append({
                    "id": rec["id"],
                    "category": category,
                    "amount": round(rec["amount"], 2),
                    "date": rec["date"].isoformat(),
                    "description": rec["description"],
                    "z_score": round(z, 2),
                    "category_mean": round(mean, 2),
                    "deviation": round(rec["amount"] - mean, 2),
                })

    anomalies.sort(key=lambda a: a["z_score"], reverse=True)
    return anomalies


def _monthly_expense_series(records):
    """Reduces the expense records to a "YYYY-MM" -> total dictionary."""
    buckets: dict[str, float] = {}
    for rec in records:
        key = rec["date"].strftime("%Y-%m")
        buckets[key] = buckets.get(key, 0.0) + rec["amount"]
    return buckets


def _score_savings_rate(income, expense):
    """Maps the savings rate onto 0-100.

    The same ((income-expense)/income) ratio as in generate_financial_advice,
    additionally converted to a score here. A 20% savings rate is taken as
    full marks (a common personal-finance threshold) and a negative rate is
    clamped to 0.
    """
    if income <= 0:

        return 50.0, 0.0
    rate = (income - expense) / income
    return max(0.0, min(100.0, (rate / 0.20) * 100.0)), rate


def _score_debt_ratio(monthly_debt_payment, monthly_income):
    """Maps the monthly debt payment / monthly income ratio onto 0-100.

    0% debt -> 100 points, 40% and above -> 0 points (the upper bound commonly
    used in credit assessment).
    """
    if monthly_income <= 0:
        return 50.0, 0.0
    ratio = monthly_debt_payment / monthly_income
    return max(0.0, min(100.0, (1.0 - ratio / 0.40) * 100.0)), ratio


def _score_volatility(monthly_totals):
    """Maps expense volatility onto 0-100.

    The coefficient of variation (stdev/mean) is used: zero volatility -> 100
    points, 50% and above -> 0 points. Predictable spending is a good
    signal.
    """
    values = [v for v in monthly_totals.values() if v > 0]
    if len(values) < 2:
        return 50.0, 0.0
    mean = statistics.fmean(values)
    if mean <= 0:
        return 50.0, 0.0
    cv = statistics.pstdev(values) / mean
    return max(0.0, min(100.0, (1.0 - cv / 0.50) * 100.0)), cv


def compute_financial_health_score(lookback_days=90, persist=True):
    """Produces and records a composite financial health score between 0 and 100.

    The components and their weights:
      * savings rate         50% -- the single strongest indicator
      * debt/income ratio    30% -- the sum of monthly instalments in active_debts
      * expense volatility   20% -- the month-to-month fluctuation in spending

    If `persist=True` a meaningful score is written to
    financial_health_history with a timestamp (for future history queries).
    Tests can use persist=False.

    Returns: {score, breakdown: {...}, computed_at, insufficient_data}
    """

    expenses = _load_transactions(
        lookback_days, _EXPENSE_TYPES, decrypt_description=False)
    incomes = _load_transactions(
        lookback_days, _INCOME_TYPES, decrypt_description=False)

    total_expense = sum(r["amount"] for r in expenses)
    total_income = sum(r["amount"] for r in incomes)
    computed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


    if total_income <= 0 and total_expense <= 0:
        return {
            "score": None,
            "breakdown": {},
            "computed_at": computed_at,
            "insufficient_data": True,
        }


    monthly_debt_payment = 0.0
    try:
        from database.db import get_active_debts
        monthly_debt_payment = sum(d.get("monthly_payment", 0.0) for d in get_active_debts())
    except sqlite3.Error:
        from utils.logging_config import get_logger
        get_logger().exception("[DB] Aylık borç yükü hesaplanamadı")
        monthly_debt_payment = 0.0


    months = max(1.0, lookback_days / 30.0)
    monthly_income = total_income / months

    savings_score, savings_rate = _score_savings_rate(total_income, total_expense)
    debt_score, debt_ratio = _score_debt_ratio(monthly_debt_payment, monthly_income)
    volatility_score, volatility_cv = _score_volatility(_monthly_expense_series(expenses))

    score = round(
        savings_score * 0.50 + debt_score * 0.30 + volatility_score * 0.20, 1
    )

    breakdown = {
        "savings_rate": round(savings_rate, 4),
        "debt_ratio": round(debt_ratio, 4),
        "expense_volatility": round(volatility_cv, 4),
        "savings_score": round(savings_score, 1),
        "debt_score": round(debt_score, 1),
        "volatility_score": round(volatility_score, 1),
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "monthly_debt_payment": round(monthly_debt_payment, 2),
        "lookback_days": lookback_days,
    }

    if persist:
        save_health_score(score, breakdown, computed_at)

    return {
        "score": score,
        "breakdown": breakdown,
        "computed_at": computed_at,
        "insufficient_data": False,
    }


def save_health_score(score, breakdown, computed_at=None):
    """Stores one health score per day; updates it if it is recomputed the same day."""
    timestamp = computed_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO financial_health_history "
            "(date, score, breakdown_json) VALUES (?, ?, ?) "
            "ON CONFLICT DO UPDATE SET "
            "date = excluded.date, score = excluded.score, "
            "breakdown_json = excluded.breakdown_json",
            (
                timestamp,
                float(score),
                json.dumps(breakdown, ensure_ascii=False),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_health_history(limit=30):
    """Returns the last N scores newest first (for a future history view)."""
    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT date, score, breakdown_json FROM financial_health_history"
            " ORDER BY id DESC LIMIT ?",
            (int(limit),),
        )
        rows = cursor.fetchall()

    history = []
    for r in rows:
        try:
            breakdown = json.loads(r["breakdown_json"]) if r["breakdown_json"] else {}
        except (ValueError, TypeError):


            breakdown = {}
        history.append({"date": r["date"], "score": r["score"], "breakdown": breakdown})
    return history


def generate_monthly_forecast(lookback_days=90, min_days=85):
    """A month-end balance forecast based on at least ~3 months of cash-flow statistics.

    The income/expense average over `lookback_days` is fed as the daily input
    to the RK4 projection (see services/projection_service) and driven forward
    to the last day of the current month. If the oldest record is more recent
    than `min_days` (that is, if there really is not close to 3 months of
    history) it returns insufficient_data=True rather than producing an
    untrustworthy estimate.
    """
    from calendar import monthrange

    from services.projection_service import project_final_wealth
    from services.queries import DashboardService


    expenses = _load_transactions(
        lookback_days, _EXPENSE_TYPES, decrypt_description=False)
    incomes = _load_transactions(
        lookback_days, _INCOME_TYPES, decrypt_description=False)
    records = expenses + incomes

    if not records:
        return {"insufficient_data": True, "days_available": 0}

    earliest = min(r["date"] for r in records)
    days_available = (datetime.now().date() - earliest).days
    if days_available < min_days:
        return {"insufficient_data": True, "days_available": days_available}

    total_expense = sum(r["amount"] for r in expenses)
    total_income = sum(r["amount"] for r in incomes)
    daily_income = total_income / lookback_days
    daily_expense = total_expense / lookback_days

    current_balance = DashboardService.get_total_balance()
    today = datetime.now().date()
    days_remaining = max(0, monthrange(today.year, today.month)[1] - today.day)

    projected_month_end_balance = project_final_wealth(
        initial_wealth=current_balance,
        daily_income=daily_income,
        daily_expense=daily_expense,
        days=days_remaining,
        r=0.0001,
    )
    savings_rate = (
        (total_income - total_expense) / total_income if total_income > 0 else 0.0
    )

    return {
        "insufficient_data": False,
        "days_available": days_available,
        "current_balance": round(current_balance, 2),
        "projected_month_end_balance": round(projected_month_end_balance, 2),
        "projected_surplus": round(projected_month_end_balance - current_balance, 2),
        "savings_rate": round(savings_rate, 4),
        "days_remaining": days_remaining,
    }


def score_label(score):
    """Converts a score into a label -- so the UI takes both the label and the
    colour from here. The labels themselves are Turkish source keys resolved
    through the i18n layer.
    """
    if score >= 80:
        return "Çok İyi"
    if score >= 60:
        return "İyi"
    if score >= 40:
        return "Orta"
    if score >= 20:
        return "Zayıf"
    return "Kritik"
