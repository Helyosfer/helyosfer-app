"""Category-based monthly budget tracking and suggestion service.

Because the amount columns could be encrypted in past versions, no aggregation
is done inside SQL; every monetary total is decrypted and computed in Python.

"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from database.db import (
    COMPLETED_TX, get_active_recurring_payments, get_connection,
)
from utils.crypto import decrypt
from utils.errors import (
    DecryptionError,
    FinancialDataIntegrityError,
    KeyUnavailableError,
)
from utils.financial_decimal import decimal_from, fiat, percentage

SECRET_KEY = "fi" + "nora_secure_2026"
EXPENSE_TYPES = {"expense", "Gider"}


def _amount(value, *, table, record_id, field="amount"):
    """Read an amount or invalidate the complete derived budget result."""
    try:
        return decimal_from(value)
    except (TypeError, ValueError):
        try:
            return decimal_from(decrypt(str(value), SECRET_KEY))
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError) as exc:
            raise FinancialDataIntegrityError(
                table, record_id, field, reason=exc
            ) from exc


def _month_shift(year, month, delta):
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def _identity(row):
    category = row["category_name"]
    if category:
        return ("category", row["type"], str(category).casefold())
    return ("name", row["type"], str(row["name"]).strip().casefold())


def _effective_plan_rows(conn, target_month, target_year):
    """Returns the concrete month records plus the latest templates not overridden by them."""
    concrete = conn.execute(
        "SELECT * FROM monthly_budget_plan "
        "WHERE target_month = ? AND target_year = ? AND is_template = 0 "
        "ORDER BY id",
        (target_month, target_year),
    ).fetchall()
    templates = conn.execute(
        "SELECT * FROM monthly_budget_plan WHERE is_template = 1 ORDER BY id"
    ).fetchall()

    concrete_keys = {_identity(row) for row in concrete}
    latest_templates = {}
    for row in templates:
        latest_templates[_identity(row)] = row
    inherited = [
        row for key, row in latest_templates.items()
        if key not in concrete_keys
    ]
    return list(concrete) + inherited


def get_effective_plan_items(target_month, target_year):
    """Returns, as a dictionary, the plan items visible in that month for the UI and the calculation engine."""
    conn = get_connection()
    try:
        rows = _effective_plan_rows(conn, int(target_month), int(target_year))
        return [dict(row) for row in rows]
    finally:
        conn.close()


def _occurrences_in_month(payment, year, month):
    from services.recurring_service import next_due_for_recurrence

    recurrence_day = (
        payment.get("recurrence_day")
        or int(str(payment["next_due_date"])[8:10])
    )

    def advance(current):
        return date.fromisoformat(next_due_for_recurrence(
            current.isoformat(), payment["frequency"], recurrence_day
        ))

    due = date.fromisoformat(payment["next_due_date"])
    month_start = date(year, month, 1)
    next_year, next_month = _month_shift(year, month, 1)
    month_end = date(next_year, next_month, 1)
    guard = 0
    while due < month_start and guard < 800:
        due = advance(due)
        guard += 1

    count = 0
    while due < month_end and guard < 800:
        if due >= month_start:
            count += 1
        due = advance(due)
        guard += 1
    return count


def get_reserved_recurring_items(target_month, target_year):
    """Returns the active subscriptions due in the target month as a read-only list."""
    items = []
    for payment in get_active_recurring_payments():
        occurrences = _occurrences_in_month(
            payment, int(target_year), int(target_month)
        )
        if not occurrences:
            continue
        if not payment.get("amount_is_valid", True):


            raise FinancialDataIntegrityError(
                "recurring_payments", payment.get("id"), "amount"
            )
        item = dict(payment)
        item["occurrences"] = occurrences
        item["reserved_amount"] = fiat(
            decimal_from(payment["amount"]) * occurrences
        )
        items.append(item)
    return items


def calculate_monthly_budget(target_month, target_year=None):
    """Returns the plan total, the subscription reservation and the spendable balance."""
    target_month = int(target_month)
    target_year = int(target_year or date.today().year)
    if not 1 <= target_month <= 12:
        raise ValueError("Ay 1 ile 12 arasında olmalıdır.")

    rows = get_effective_plan_items(target_month, target_year)
    planned_income = sum(
        _amount(
            row["amount"], table="monthly_budget_plan", record_id=row["id"]
        ) for row in rows
        if row["type"] in ("Gelir", "income")
    )
    planned_expense = sum(
        _amount(
            row["amount"], table="monthly_budget_plan", record_id=row["id"]
        ) for row in rows
        if row["type"] in EXPENSE_TYPES
    )
    recurring_items = get_reserved_recurring_items(target_month, target_year)
    reserved = sum(
        (item["reserved_amount"] for item in recurring_items), Decimal("0")
    )
    return {
        "planned_income": fiat(planned_income),
        "planned_expense": fiat(planned_expense),
        "reserved_recurring": fiat(reserved),
        "remaining_budget": fiat(planned_income - planned_expense - reserved),
    }


PLAN_ITEM_TYPES = ("income", "expense", "Gelir", "Gider")


def save_plan_item(
    *,
    item_type,
    name,
    amount,
    month,
    year,
    category=None,
    rollover_enabled=False,
    is_template=False,
    alert_threshold_pct=80,
    item_id=None,
    editing_a_template=False,
    propagate_to_months=(),
):
    """Creates or updates a budget plan item -- in a single transaction.

    WHY IN THE SERVICE LAYER: this write was the ONLY path INTO the tables
    holding money that did not pass through a service boundary. The SQL sat
    directly in the interface layer, which meant the validation for
    `monthly_budget_plan.amount` was only the interface's own check
    (amount parsing + `amount <= 0`). The interface cannot produce `nan`/`inf`
    today (`parse_amount` accepts only digits and separators), so it was NOT a
    known hole; but for as long as the rule lived in the interface, a second
    caller (an import, a script, a test) would bypass it without ever seeing
    it. Every other monetary write passes through the `fiat()` boundary; this
    one now does too.

    The amount is stored rounded to the kurus -- the same policy as the other
    money boundaries in the project (`insert_debt`,
    `insert_recurring_payment`).

    If `propagate_to_months` is supplied the same item is COPIED into those
    months as well, and the copies are never templates. The copying happens in
    the SAME commit as the original write: a half-finished propagation would
    leave an incomplete plan the user cannot see.
    """
    item_type = str(item_type or "").strip()
    if item_type not in PLAN_ITEM_TYPES:
        raise ValueError(f"Bilinmeyen bütçe kalemi türü: {item_type!r}")

    name = str(name or "").strip()
    if not name:
        raise ValueError("Bütçe kalemi adı boş olamaz.")

    try:
        amount_decimal = fiat(amount)
    except (TypeError, ValueError) as exc:
        raise ValueError("Bütçe kalemi tutarı geçerli bir sayı olmalıdır.") from exc
    if amount_decimal <= 0:
        raise ValueError("Bütçe kalemi tutarı 0'dan büyük olmalıdır.")

    month = int(month)
    if not 1 <= month <= 12:
        raise ValueError("Ay 1 ile 12 arasında olmalıdır.")
    year = int(year)

    alert_threshold_pct = int(alert_threshold_pct)
    if not 1 <= alert_threshold_pct <= 100:
        raise ValueError("Uyarı eşiği 1 ile 100 arasında olmalıdır.")

    targets = sorted({int(target) for target in propagate_to_months})
    for target in targets:
        if not 1 <= target <= 12:
            raise ValueError("Kopyalanacak ay 1 ile 12 arasında olmalıdır.")

    stored_amount = float(amount_decimal)
    rollover = int(bool(rollover_enabled))
    template = int(bool(is_template))

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        if item_id is not None and not editing_a_template:
            cursor.execute(
                "UPDATE monthly_budget_plan SET"
                " type=?, name=?, amount=?, target_month=?, target_year=?,"
                " category_name=?, rollover_enabled=?, is_template=?,"
                " alert_threshold_pct=?"
                " WHERE id=? AND target_month=? AND target_year=?",
                (item_type, name, stored_amount, month, year, category,
                 rollover, template, alert_threshold_pct,
                 int(item_id), month, year),
            )
        else:


            cursor.execute(
                "INSERT INTO monthly_budget_plan"
                " (type,name,amount,target_month,target_year,category_name,"
                "  rollover_enabled,is_template,alert_threshold_pct)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (item_type, name, stored_amount, month, year, category,
                 rollover, 0 if item_id is not None else template,
                 alert_threshold_pct),
            )
        for target in targets:
            if target == month:
                continue
            cursor.execute(
                "INSERT INTO monthly_budget_plan"
                " (type,name,amount,target_month,target_year,category_name,"
                "  rollover_enabled,is_template,alert_threshold_pct)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (item_type, name, stored_amount, target, year, category,
                 rollover, 0, alert_threshold_pct),
            )
        conn.commit()
    finally:
        conn.close()


def delete_plan_item(item_id):
    """Removes a plan item; returns True if it existed.

    Deleting a template removes it from every month that inherited it.
    """
    conn = get_connection()
    try:
        cursor = conn.execute(
            "DELETE FROM monthly_budget_plan WHERE id = ?", (int(item_id),)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def apply_plan_to_year_end(source_month, source_year):
    """Copies the current month's plan items through to the end of the year (December).

    Once the user has entered their fixed
    income/expense/investments and confirmed "Would you like to use this as
    your current plan?", this month's CONCRETE (non-template) items are
    carried into the remaining months (source_month+1 ... December). Template
    items (is_template=1) are not copied, since they already apply to every
    month. If an item with the same identity (category, or name+type) already
    exists in the target month, that item is skipped -- so confirming twice
    produces no duplicates (idempotent). Returns the total number of items
    added.
    """
    source_month = int(source_month)
    source_year = int(source_year)
    conn = get_connection()
    copied = 0
    try:
        cursor = conn.cursor()
        source_items = cursor.execute(
            "SELECT * FROM monthly_budget_plan "
            "WHERE target_month = ? AND target_year = ? AND is_template = 0 "
            "ORDER BY id",
            (source_month, source_year),
        ).fetchall()
        if not source_items:
            return 0
        for target_month in range(source_month + 1, 13):
            existing = cursor.execute(
                "SELECT * FROM monthly_budget_plan "
                "WHERE target_month = ? AND target_year = ? AND is_template = 0",
                (target_month, source_year),
            ).fetchall()
            existing_keys = {_identity(row) for row in existing}
            for row in source_items:
                if _identity(row) in existing_keys:
                    continue
                cursor.execute(
                    "INSERT INTO monthly_budget_plan "
                    "(type, name, amount, target_month, target_year, "
                    " category_name, rollover_enabled, is_template, "
                    " alert_threshold_pct) VALUES (?,?,?,?,?,?,?,?,?)",
                    (row["type"], row["name"], row["amount"], target_month,
                     source_year, row["category_name"],
                     row["rollover_enabled"], 0, row["alert_threshold_pct"]),
                )
                copied += 1
        conn.commit()
    finally:
        conn.close()
    return copied


def _actual_category_totals(target_month, target_year):
    conn = get_connection()
    try:


        rows = conn.execute(
            "SELECT id, category, amount FROM transactions "
            "WHERE type IN ('expense', 'Gider') "
            "AND strftime('%m', transaction_date) = ? "
            "AND strftime('%Y', transaction_date) = ? "
            f"AND {COMPLETED_TX}",
            (f"{int(target_month):02d}", str(int(target_year))),
        ).fetchall()
    finally:
        conn.close()
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for record_id, category, amount in rows:
        totals[str(category or "")] += _amount(
            amount, table="transactions", record_id=record_id
        )
    return totals


def get_category_budget_progress(target_month, target_year):
    """Compares category plans with the actual expenses in the same month/year."""
    plan_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    thresholds = {}
    rollover_flags = {}
    for row in get_effective_plan_items(target_month, target_year):
        category = row.get("category_name")
        if not category or row["type"] not in EXPENSE_TYPES:
            continue
        plan_totals[category] += _amount(
            row["amount"], table="monthly_budget_plan", record_id=row["id"]
        )
        thresholds[category] = int(row.get("alert_threshold_pct") or 80)
        rollover_flags[category] = bool(row.get("rollover_enabled"))

    actuals = _actual_category_totals(target_month, target_year)
    result = []
    for category, planned in plan_totals.items():
        actual = actuals.get(category, Decimal("0"))
        result.append({
            "category": category,
            "planned": fiat(planned),
            "actual": fiat(actual),
            "pct": percentage(actual / planned * 100) if planned else None,
            "remaining": fiat(planned - actual),
            "alert_threshold_pct": thresholds[category],
            "rollover_enabled": rollover_flags[category],
        })
    return sorted(result, key=lambda item: item["category"].casefold())


def get_effective_limit(category_name, target_month, target_year):
    """Adjusts the category limit by the previous month's balance ONLY.

    No chained carry-over: the previous month's own ``planned - actual``
    result is used; whatever it inherited from earlier months is not carried
    again.
    """
    current = next((
        item for item in get_category_budget_progress(target_month, target_year)
        if item["category"] == category_name
    ), None)
    if current is None:
        return 0.0
    if not current["rollover_enabled"]:
        return current["planned"]

    prev_year, prev_month = _month_shift(
        int(target_year), int(target_month), -1
    )
    previous = next((
        item for item in get_category_budget_progress(prev_month, prev_year)
        if item["category"] == category_name
    ), None)
    # An int, not 0.0: `planned` is a Decimal and Decimal + float raises.
    carry = previous["remaining"] if previous else 0
    return round(current["planned"] + carry, 2)


def suggest_category_budget(category_name, lookback_months=3):
    """The monthly average of actual category expenses over the last N completed months."""
    count = int(lookback_months)
    if count <= 0:
        raise ValueError("lookback_months pozitif olmalıdır.")
    today = date.today()
    totals = []
    any_data = False
    for offset in range(1, count + 1):
        year, month = _month_shift(today.year, today.month, -offset)
        total = _actual_category_totals(month, year).get(category_name, 0.0)
        totals.append(total)
        any_data = any_data or total > 0
    return round(sum(totals) / count, 2) if any_data else None


def get_budget_trend(months=6, end_date=None):
    """Returns the aggregate category plan/actual series going backwards, the last month included."""
    end = end_date or date.today()
    series = []
    for offset in reversed(range(int(months))):
        year, month = _month_shift(end.year, end.month, -offset)
        progress = get_category_budget_progress(month, year)
        series.append({
            "label": f"{month:02d}/{year}",
            "planned": round(sum(item["planned"] for item in progress), 2),
            "actual": round(sum(item["actual"] for item in progress), 2),
        })
    return series
