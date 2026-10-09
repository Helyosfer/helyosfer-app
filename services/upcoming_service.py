"""What needs the user's attention soon: pending transactions, recurring
payments, and the automatic debt instalments and savings contributions that
are due within a week or already overdue.
"""

from __future__ import annotations

import datetime

UPCOMING_WINDOW_DAYS = 7
PENDING, RECURRING, DEBT, SAVING = "pending", "recurring", "debt", "saving"


def collect_upcoming(today: datetime.date | None = None) -> list[dict]:
    """Returns [{kind, name, date, amount, income, automatic}], soonest first.

    A recurring payment whose stored date cannot be read is left out rather
    than guessed at; one whose amount cannot be read is listed without one.
    """
    from database.db import get_active_recurring_payments
    from services.transaction_service import TransactionService

    today = today or datetime.date.today()
    items = []

    for pending in TransactionService.get_pending_transactions():
        items.append({
            "kind": PENDING,
            "name": str(pending.get("description") or ""),
            "date": pending.get("execution_date") or "",
            "amount": pending.get("amount"),
            "income": pending.get("type") == "income",
            "automatic": True,
        })

    for payment in get_active_recurring_payments():
        raw_due = payment.get("next_due_date")
        try:
            due = datetime.date.fromisoformat(str(raw_due)[:10])
        except (TypeError, ValueError):
            continue
        if (due - today).days > UPCOMING_WINDOW_DAYS:
            continue
        items.append({
            "kind": RECURRING,
            "name": str(payment.get("name") or ""),
            "date": due.isoformat(),
            "amount": payment["amount"] if payment.get("amount_is_valid", True) else None,
            "income": payment.get("transaction_type") == "income",
            "automatic": bool(payment.get("auto_deduct")),
        })

    items.extend(_automatic_debts(today))
    items.extend(_automatic_savings(today))
    items.sort(key=lambda entry: (not entry["date"], entry["date"]))
    return items


def _soon(day, today) -> bool:
    return day is not None and (day - today).days <= UPCOMING_WINDOW_DAYS


def _automatic_debts(today: datetime.date) -> list[dict]:
    """The next instalment of every debt that is paid automatically."""
    from database.db import get_active_debts
    from services.scheduled_service import next_debt_day

    items = []
    for debt in get_active_debts():
        day = next_debt_day(debt, today)
        if not _soon(day, today):
            continue
        items.append({
            "kind": DEBT,
            "name": str(debt.get("debt_name") or ""),
            "date": day.isoformat(),
            "amount": debt["monthly_payment"],
            "income": False,
            "automatic": True,
        })
    return items


def _automatic_savings(today: datetime.date) -> list[dict]:
    """The next contribution of every savings goal that has one."""
    from services.savings_auto_service import get_contributions, next_day
    from services.savings_service import STATUS_COMPLETED, SavingsService

    plans = get_contributions()
    if not plans:
        return []
    goals = {goal["goal_uid"]: goal for goal in SavingsService.get_goals()}
    items = []
    for goal_uid, plan in plans.items():
        goal = goals.get(goal_uid)
        if goal is None or goal["status"] == STATUS_COMPLETED:
            continue
        day = next_day(plan, today)
        needed = float(goal["target_amount"]) - float(goal["current_amount"])
        if not _soon(day, today) or needed <= 0:
            continue
        items.append({
            "kind": SAVING,
            "name": str(goal.get("goal_name") or ""),
            "date": day.isoformat(),
            "amount": min(float(plan["amount"]), needed),
            "income": False,
            "automatic": True,
        })
    return items
