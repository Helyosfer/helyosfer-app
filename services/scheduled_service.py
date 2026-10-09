"""Applies everything that has fallen due: pending transactions, automatic
recurring payments and automatic debt instalments.

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


def process_due_items(today: datetime.date | None = None) -> bool:
    """Returns True if any balance changed."""
    from database.db import (
        DEFAULT_ACCOUNT_ID, get_active_debts, get_active_recurring_payments,
        process_due_recurring_payment,
    )
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
            if datetime.date.fromisoformat(payment["next_due_date"]) > today:
                continue
            process_due_recurring_payment(payment)
            changed = True
        except _ITEM_ERRORS:
            get_logger().exception(
                "Tekrarlanan ödeme işlenemedi (id=%s), diğerleri sürdürülüyor",
                payment.get("id"),
            )

    month = today.strftime("%Y-%m")
    for debt in get_active_debts():
        count = due_debt_installments(debt, today)
        if not count:
            continue
        try:
            if DebtPaymentService.pay_auto(debt["id"], DEFAULT_ACCOUNT_ID, count, month):
                changed = True
        except _ITEM_ERRORS:
            get_logger().exception(
                "Otomatik borç taksiti işlenemedi (id=%s), diğerleri sürdürülüyor",
                debt.get("id"),
            )
    return changed
