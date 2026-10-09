"""Applies everything that has fallen due: pending transactions, automatic
recurring payments, automatic debt instalments and savings contributions.

Run once after sign-in, off the interface thread. Each item is handled on its
own: one record that cannot be processed is logged and the rest continue, so a
single damaged row never holds up everyone else's money.
"""

from __future__ import annotations

import calendar
import datetime
import sqlite3

from utils.errors import HelyosferError
from utils.logging_config import get_logger

_ITEM_ERRORS = (sqlite3.Error, HelyosferError, ValueError, TypeError, ArithmeticError)

# More periods than any profile can owe; it only keeps a damaged due date
# from being charged without end.
_CATCH_UP_LIMIT = 1200
CREDIT_CARD = "credit_card"


def due_debt_installments(debt: dict, today: datetime.date) -> int:
    """How many instalments automatic payment owes for this debt today.

    Nothing before the debt's pay day this month, nothing twice in one month,
    and missed months are caught up -- never more than what remains.
    """
    if not debt.get("is_auto_pay"):
        return 0
    remaining = debt["total_installments"] - debt["paid_installments"]
    if remaining <= 0:
        return 0
    days_in_month = calendar.monthrange(today.year, today.month)[1]
    pay_day = min(debt.get("auto_pay_day") or 1, days_in_month)
    if today.day < pay_day:
        return 0
    last = debt.get("last_auto_pay_date")
    if last == today.strftime("%Y-%m"):
        return 0
    if last:
        last_year, last_month = (int(part) for part in last.split("-"))
        missed = (today.year - last_year) * 12 + (today.month - last_month)
    else:
        missed = 1
    return min(max(1, missed), remaining)


def due_debt_days(debt: dict, today: datetime.date) -> list[datetime.date]:
    """The pay days automatic payment owes for this debt, oldest first.

    One for every month `due_debt_installments` counts: the months after the
    last one paid, or this month when none was.
    """
    count = due_debt_installments(debt, today)
    if not count:
        return []
    last = debt.get("last_auto_pay_date")
    if last:
        year, month = (int(part) for part in last.split("-"))
        first = year * 12 + month
    else:
        first = today.year * 12 + today.month - 1
    days = []
    for index in range(first, first + count):
        year, month = index // 12, index % 12 + 1
        day = min(debt.get("auto_pay_day") or 1, calendar.monthrange(year, month)[1])
        days.append(datetime.date(year, month, day))
    # A clock that was set back must not pay for days that have not come.
    return [day for day in days if day <= today]


def auto_pay_account(debt: dict, accounts: list[dict]):
    """The account an automatic instalment is taken from, or None.

    The one chosen for the debt while it exists; otherwise the oldest account
    that is not a credit card. A loan is never paid from a card.
    """
    usable = sorted(
        account["id"] for account in accounts if account.get("account_type") != CREDIT_CARD
    )
    chosen = debt.get("auto_pay_account_id")
    if chosen in usable:
        return chosen
    return usable[0] if usable else None


def _charge_what_is_due(payment: dict, today: datetime.date) -> bool:
    """Charges every period of an automatic payment that has fallen due.

    A profile that was not opened for a while owes more than one period.
    Each is written on the day it was due, as the bank took it.
    """
    from database.db import process_due_recurring_payment
    from services.recurring_service import next_due_for_recurrence

    payment = dict(payment)
    charged = False
    for _ in range(_CATCH_UP_LIMIT):
        due = str(payment["next_due_date"])
        if datetime.date.fromisoformat(due[:10]) > today:
            break
        if not process_due_recurring_payment(payment, on_due_date=True):
            break
        charged = True
        payment["next_due_date"] = next_due_for_recurrence(
            due[:10], payment["frequency"],
            payment.get("recurrence_day") or int(due[8:10]),
        )
    return charged


def process_due_items(today: datetime.date | None = None) -> bool:
    """Returns True if any balance changed."""
    from database.db import get_active_debts, get_active_recurring_payments
    from services.account_service import AccountService
    from services.debt_payment_service import DebtPaymentService
    from services.transaction_service import TransactionService

    if not AccountService.has_any_account():
        return False
    today = today or datetime.date.today()
    changed = False

    try:
        changed = bool(TransactionService.settle_due_transactions()) or changed
    except _ITEM_ERRORS:
        get_logger().exception("Bekleyen işlemler işlenemedi")

    for payment in get_active_recurring_payments():
        if not payment["auto_deduct"]:
            continue
        try:
            changed = _charge_what_is_due(payment, today) or changed
        except _ITEM_ERRORS:
            get_logger().exception(
                "Tekrarlanan ödeme işlenemedi (id=%s), diğerleri sürdürülüyor",
                payment.get("id"),
            )

    accounts = None
    for debt in get_active_debts():
        days = due_debt_days(debt, today)
        if not days:
            continue
        try:
            if accounts is None:
                accounts = AccountService.get_accounts()
            account_id = auto_pay_account(debt, accounts)
            if account_id is None:
                continue
            for day in days:
                if DebtPaymentService.pay_auto(
                    debt["id"], account_id, 1, day.strftime("%Y-%m"), paid_on=day,
                ):
                    changed = True
        except _ITEM_ERRORS:
            get_logger().exception(
                "Otomatik borç taksiti işlenemedi (id=%s), diğerleri sürdürülüyor",
                debt.get("id"),
            )

    try:
        from services.savings_auto_service import process_due_contributions

        changed = bool(process_due_contributions(today)) or changed
    except _ITEM_ERRORS:
        get_logger().exception("Otomatik birikim katkıları işlenemedi")
    return changed
