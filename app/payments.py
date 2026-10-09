"""Controllers for debts, pending transactions and recurring payments."""

from __future__ import annotations

import datetime
import sqlite3

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, _Mutating, read_amount
from app.controllers import display_title, format_amount, short_date
from services.background_task_manager import BackgroundTaskManager
from app.language import later, say, tr
from utils.errors import HelyosferError
from utils.logging_config import get_logger

FREQUENCIES = (
    ("weekly", later("Weekly")),
    ("biweekly", later("Every two weeks")),
    ("monthly", later("Monthly")),
    ("quarterly", later("Every three months")),
    ("yearly", later("Yearly")),
)


def read_count(text: str, label: str, low: int, high: int) -> int:
    try:
        value = int((text or "").strip())
    except ValueError:
        raise FormError(say("Enter the {0} as a whole number.", label)) from None
    if not low <= value <= high:
        raise FormError(say("The {0} must be between {1} and {2}.", label, low, high))
    return value


def read_day(text: str) -> datetime.date:
    try:
        return datetime.datetime.strptime((text or "").strip(), "%d.%m.%Y").date()
    except ValueError:
        raise FormError(say("Enter the date as DD.MM.YYYY, for example 08.10.2026.")) from None


def due_phrase(iso_date: str, today: datetime.date | None = None) -> tuple[str, bool]:
    """('08 Oct · in 3 days', overdue?)"""
    today = today or datetime.date.today()
    day = datetime.date.fromisoformat(iso_date[:10])
    delta = (day - today).days
    if delta < 0:
        when = say("1 day overdue") if delta == -1 else say("{0} days overdue", -delta)
    elif delta == 0:
        when = "today"
    elif delta == 1:
        when = "tomorrow"
    else:
        when = say("in {0} days", delta)
    return f"{short_date(iso_date)}  ·  {when}", delta < 0


class _Listing(_Mutating):
    """A controller that shows one loaded snapshot and reloads after writes.

    Subclasses declare their own `changed` signal: a property may only name a
    notify signal defined on its own class.
    """

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self.dataChanged.connect(self.refresh)

    def _fetch(self):
        raise NotImplementedError

    def _show(self, data) -> None:
        raise NotImplementedError

    @Slot()
    def refresh(self):
        self._tasks.submit(
            f"load-{id(self)}", lambda _cancel: self._fetch(),
            on_success=self._loaded, on_error=self._load_failed, replace=True,
        )

    def _loaded(self, data) -> None:
        self._show(data)
        self.changed.emit()

    def _load_failed(self, error) -> None:
        get_logger().exception(
            "Liste yüklenemedi.", exc_info=(type(error), error, error.__traceback__),
        )
        self._set_message(say("This list could not be loaded."))


class DebtsController(_Listing):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._debts: list[dict] = []
        self._pending: list[dict] = []
        self._total = "—"
        self._monthly = "—"

    @Property("QVariantList", notify=changed)
    def debts(self):
        return self._debts

    @Property("QVariantList", notify=changed)
    def pending(self):
        return self._pending

    @Property(str, notify=changed)
    def totalText(self):
        return self._total

    @Property(str, notify=changed)
    def monthlyText(self):
        return self._monthly

    @staticmethod
    def _fetch():
        from database.db import get_active_debts
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        names = {a["id"]: a["name"] for a in AccountService.get_accounts()}
        return get_active_debts(), TransactionService.get_pending_transactions(), names

    def _show(self, data) -> None:
        debts, pending, names = data
        views = []
        total = monthly = 0.0
        for debt in debts:
            remaining = debt["total_installments"] - debt["paid_installments"]
            if remaining <= 0:
                continue
            owed = remaining * debt["monthly_payment"]
            total += owed
            monthly += debt["monthly_payment"]
            views.append({
                "id": debt["id"],
                "name": debt["debt_name"],
                "remainingText": f"{format_amount(owed)} ₺",
                "monthlyText": f"{format_amount(debt['monthly_payment'])} ₺",
                "progress": debt["paid_installments"] / debt["total_installments"],
                "progressText": (
                    say("{0} of {1} paid", debt['paid_installments'], debt['total_installments'])
                ),
                "remainingCount": remaining,
                "autoPay": debt["is_auto_pay"],
                "autoPayDay": debt["auto_pay_day"],
            })
        self._debts = views
        self._total = f"{format_amount(total)} ₺"
        self._monthly = f"{format_amount(monthly)} ₺"
        self._pending = [
            {
                "id": item["id"],
                "due": due_phrase(item["execution_date"])[0],
                "title": display_title(item["description"]),
                "account": names.get(item["account_id"], ""),
                "amount": ("+" if item["type"] == "income" else "−")
                + format_amount(item["amount"]) + " ₺",
                "income": item["type"] == "income",
            }
            for item in pending
        ]

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, bool, str)
    def addDebt(self, name, monthly_text, installments_text, auto_pay, day_text):
        def work():
            from services.debt_payment_service import DebtPaymentService

            DebtPaymentService.create_debt(
                name,
                read_amount(monthly_text, say("monthly payment")),
                read_count(installments_text, say("number of installments"), 1, 600),
                auto_pay,
                read_count(day_text, say("payment day"), 1, 31) if auto_pay else 1,
            )

        self._mutate(work)

    @Slot(int, int, int)
    def pay(self, debt_id, account_id, installments):
        """`installments` of 0 closes the debt by paying everything left."""
        def work():
            from services.debt_payment_service import DebtPaymentService

            if account_id < 0:
                raise FormError(say("Choose the account to pay from."))
            if installments < 0:
                raise FormError(say("Enter how many installments to pay."))
            DebtPaymentService.pay_manual(debt_id, account_id, installments or None)

        self._mutate(work)

    @Slot(int, bool, str)
    def setAutoPay(self, debt_id, enabled, day_text):
        def work():
            from database.db import update_debt_auto_pay

            day = read_count(day_text, say("payment day"), 1, 31) if enabled else 1
            update_debt_auto_pay(debt_id, enabled, day)

        self._mutate(work)

    @Slot(int)
    def cancelPending(self, transaction_id):
        from services.transaction_service import TransactionService

        self._mutate(
            lambda: TransactionService.cancel_pending_transaction(transaction_id),
            announce=False,
        )

    @Slot(int, str)
    def reschedule(self, transaction_id, date_text):
        def work():
            from services.transaction_service import TransactionService

            day = read_day(date_text)
            if day <= datetime.date.today():
                raise FormError(say("Choose a date after today."))
            TransactionService.reschedule_pending_transaction(
                transaction_id, day.isoformat()
            )

        self._mutate(work)


class RecurringController(_Listing):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._items: list[dict] = []
        self._monthly = "—"

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property(str, notify=changed)
    def monthlyText(self):
        return self._monthly

    @Property("QVariantList", constant=True)
    def frequencies(self):
        return [{"key": key, "label": say(label)} for key, label in FREQUENCIES]

    @staticmethod
    def _fetch():
        from database.db import get_active_recurring_payments
        from services.account_service import AccountService

        names = {a["id"]: a["name"] for a in AccountService.get_accounts()}
        return get_active_recurring_payments(), names

    def _show(self, data) -> None:
        payments, names = data
        per_month = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1,
                     "quarterly": 1 / 3, "yearly": 1 / 12}
        labels = dict(FREQUENCIES)
        monthly = 0.0
        views = []
        for payment in payments:
            income = payment["transaction_type"] == "income"
            valid = payment.get("amount_is_valid", True)
            if valid and not income:
                monthly += float(payment["amount"]) * per_month.get(payment["frequency"], 1)
            due, overdue = due_phrase(payment["next_due_date"])
            views.append({
                "id": payment["id"],
                "name": payment["name"],
                "amountText": (
                    ("+" if income else "") + format_amount(payment["amount"]) + " ₺"
                    if valid else "—"
                ),
                "category": tr(payment["category"] or ""),
                "frequency": say(labels.get(payment["frequency"], payment["frequency"])),
                "due": due,
                "overdue": overdue,
                "automatic": payment["auto_deduct"],
                "income": income,
                "account": names.get(payment["account_id"], ""),
                "valid": valid,
            })
        self._items = views
        self._monthly = f"{format_amount(monthly)} ₺"

    @staticmethod
    def _payment(payment_id: int) -> dict:
        from database.db import get_active_recurring_payments

        for payment in get_active_recurring_payments():
            if payment["id"] == payment_id:
                return payment
        raise FormError(say("This payment is no longer active."))

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, str, str, str, bool, int)
    def add(self, kind, name, amount_text, category, frequency, first_due_text,
            automatic, account_id):
        def work():
            from database.db import insert_recurring_payment

            if not (name or "").strip():
                raise FormError(say("Enter a name."))
            if account_id < 0:
                raise FormError(say("Choose an account."))
            if not category:
                raise FormError(say("Choose a category."))
            first_due = read_day(first_due_text)
            insert_recurring_payment(
                name.strip(), read_amount(amount_text, say("amount")), category,
                frequency, first_due.isoformat(), automatic,
                account_id=account_id, recurrence_day=first_due.day,
                transaction_type=kind,
            )

        self._mutate(work)

    @Slot(int)
    def payNow(self, payment_id):
        from database.db import process_due_recurring_payment

        self._mutate(
            lambda: process_due_recurring_payment(self._payment(payment_id)),
            announce=False,
        )

    @Slot(int)
    def skipNext(self, payment_id):
        from services.recurring_service import skip_next_occurrence

        self._mutate(lambda: skip_next_occurrence(payment_id), announce=False)

    @Slot(int, str)
    def changeAmount(self, payment_id, amount_text):
        def work():
            from services.recurring_service import update_subscription_amount

            update_subscription_amount(payment_id, read_amount(amount_text, say("amount")))

        self._mutate(work)

    @Slot(int, result=str)
    def chargeThisMonth(self, payment_id):
        """This month's automatic charge for the payment, formatted, or ''."""
        from services.recurring_service import find_current_period_charge

        try:
            charge = find_current_period_charge(payment_id)
        except (sqlite3.Error, HelyosferError, ValueError) as error:
            get_logger().exception(
                "Dönem ücreti okunamadı.",
                exc_info=(type(error), error, error.__traceback__),
            )
            return ""
        return f"{format_amount(charge['amount'])} ₺" if charge else ""

    @Slot(int, bool)
    def cancel(self, payment_id, refund):
        def work():
            from services.recurring_service import (
                cancel_subscription, refund_current_period_charge,
            )

            if refund:
                refund_current_period_charge(payment_id)
            cancel_subscription(payment_id)

        self._mutate(work)
