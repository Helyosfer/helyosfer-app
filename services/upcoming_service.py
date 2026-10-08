"""What needs the user's attention soon: pending transactions and recurring
payments that are due within a week or already overdue.
"""

from __future__ import annotations

import datetime

UPCOMING_WINDOW_DAYS = 7
PENDING, RECURRING = "pending", "recurring"


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

    items.sort(key=lambda entry: (not entry["date"], entry["date"]))
    return items
