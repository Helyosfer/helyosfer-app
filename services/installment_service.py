"""A card purchase in installments, as the card's statements carry it.

The whole amount is charged to the card on the day of the purchase, so the
balance needs nothing more. What the plan adds is the view a statement gives:
how many installments have been billed, how much each one is, when the next
one falls and what is still to come.

Nothing about that is stored as it happens. It follows from the day of the
purchase, the card's statement day and today, so it is right however long
the application was closed.
"""

from __future__ import annotations

import calendar
import datetime

from utils.financial_decimal import decimal_from, fiat


def _in_month(year: int, month: int, day: int) -> datetime.date:
    return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def billing_days(bought: datetime.date, statement_day, count: int) -> list[datetime.date]:
    """The days the installments of a purchase are billed on, in order.

    With a statement day, the first is the first statement on or after the
    purchase. A card without one bills a month after the purchase, on the day
    of the month it was made. A day a month does not have falls on its last.
    """
    try:
        day = int(statement_day or 0)
    except (TypeError, ValueError):
        day = 0
    index = bought.year * 12 + bought.month - 1
    if 1 <= day <= 31:
        if _in_month(bought.year, bought.month, day) < bought:
            index += 1
    else:
        day = bought.day
        index += 1
    return [
        _in_month((index + step) // 12, (index + step) % 12 + 1, day)
        for step in range(max(0, int(count)))
    ]


def card_installments(account_id, today: datetime.date | None = None) -> list[dict]:
    """The installment purchases on a card that still have something to bill.

    Each: `transaction_id` (the purchase, or None when it cannot be found),
    `description`, `monthly_amount`, `total_amount`, `total_installments`,
    `billed_installments`, `remaining_amount` and `next_date`. The one billed
    soonest comes first.
    """
    from database.db import get_connection
    from services.account_service import AccountService
    from services.transaction_service import TransactionService

    today = today or datetime.date.today()
    account = AccountService.get_account(account_id)
    if account is None:
        return []
    plans = TransactionService.get_installment_plans(account_id)
    if not plans:
        return []

    conn = get_connection()
    try:
        purchases = {
            row[1]: row[0] for row in conn.execute(
                "SELECT id, transaction_date FROM transactions WHERE account_id = ?",
                (int(account_id),),
            )
        }
    finally:
        conn.close()

    ongoing = []
    for plan in plans:
        try:
            bought = datetime.date.fromisoformat(str(plan["created_at"])[:10])
        except ValueError:
            continue
        total = int(plan["total_installments"])
        days = billing_days(bought, account.get("statement_date"), total)
        billed = sum(1 for day in days if day <= today)
        if billed >= total:
            continue
        # The last installment carries what rounding left over.
        remaining = fiat(
            decimal_from(plan["total_amount"]) - decimal_from(plan["monthly_amount"]) * billed
        )
        ongoing.append({
            "transaction_id": purchases.get(plan["created_at"]),
            "description": plan["description"],
            "monthly_amount": float(plan["monthly_amount"]),
            "total_amount": float(plan["total_amount"]),
            "total_installments": total,
            "billed_installments": billed,
            "remaining_amount": float(remaining),
            "next_date": days[billed],
        })
    return sorted(ongoing, key=lambda item: (item["next_date"], item["description"]))
