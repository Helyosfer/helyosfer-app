"""Controllers for savings goals and the planning tools."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, _Mutating, read_amount
from app.controllers import format_amount, short_date
from app.payments import _Listing, read_count, read_day
from services.background_task_manager import BackgroundTaskManager


def months_between(start: datetime.date, end: datetime.date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


class SavingsController(_Listing):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._goals: list[dict] = []
        self._saved = "—"
        self._target = "—"

    @Property("QVariantList", notify=changed)
    def goals(self):
        return self._goals

    @Property(str, notify=changed)
    def savedText(self):
        return self._saved

    @Property(str, notify=changed)
    def targetText(self):
        return self._target

    @staticmethod
    def _fetch():
        from services.savings_service import SavingsService

        return SavingsService.get_goals()

    def _show(self, goals) -> None:
        today = datetime.date.today()
        views = []
        saved = target = 0.0
        for goal in goals:
            current = float(goal["current_amount"] or 0)
            wanted = float(goal["target_amount"] or 0)
            remaining = max(wanted - current, 0.0)
            saved += current
            target += wanted
            done = remaining <= 0
            pace = ""
            due = ""
            if goal["target_date"]:
                try:
                    day = datetime.date.fromisoformat(str(goal["target_date"])[:10])
                except ValueError:
                    day = None
                if day:
                    due = f"by {short_date(day.isoformat())} {day.year}"
                    months = months_between(today, day)
                    if not done and months > 0:
                        pace = f"{format_amount(remaining / months)} ₺ a month reaches it in time"
                    elif not done:
                        pace = "The target date has passed"
            views.append({
                "id": goal["id"],
                "uid": goal["goal_uid"] or "",
                "name": goal["goal_name"],
                "savedText": f"{format_amount(current)} ₺",
                "targetText": f"{format_amount(wanted)} ₺",
                "remainingText": f"{format_amount(remaining)} ₺",
                "progress": min(1.0, current / wanted) if wanted > 0 else 0.0,
                "percent": f"{min(100.0, current / wanted * 100):.0f} %" if wanted > 0 else "",
                "due": due,
                "pace": pace,
                "done": done,
                "hasMoney": current > 0,
            })
        self._goals = views
        self._saved = f"{format_amount(saved)} ₺"
        self._target = f"{format_amount(target)} ₺"

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str)
    def addGoal(self, name, target_text, date_text):
        def work():
            from services.savings_service import SavingsService

            if not (name or "").strip():
                raise FormError("Enter a name for the goal.")
            target_date = None
            if (date_text or "").strip():
                day = read_day(date_text)
                if day <= datetime.date.today():
                    raise FormError("Choose a target date after today.")
                target_date = day.isoformat()
            SavingsService.create_goal(
                name.strip(), read_amount(target_text, "target amount"), target_date
            )

        self._mutate(work)

    @Slot(int, str, str, int, bool)
    def move(self, goal_id, goal_uid, amount_text, account_id, deposit):
        """Moves money into the goal (`deposit`) or back out of it."""
        def work():
            from services.savings_service import SavingsService

            if account_id < 0:
                raise FormError("Choose an account.")
            amount = read_amount(amount_text, "amount")
            action = (
                SavingsService.deposit_to_goal if deposit
                else SavingsService.withdraw_from_goal
            )
            action(goal_id, amount, account_id, goal_uid=goal_uid or None)

        self._mutate(work)

    @Slot(int, str, int)
    def deleteGoal(self, goal_id, goal_uid, account_id):
        """Deletes the goal; any money in it goes back to `account_id`."""
        def work():
            from services.savings_service import SavingsService

            goal = next(
                (g for g in SavingsService.get_goals() if g["id"] == goal_id), None
            )
            holds_money = bool(goal and float(goal["current_amount"] or 0) > 0)
            if holds_money and account_id < 0:
                raise FormError("Choose the account that receives the saved money.")
            SavingsService.delete_goal(
                goal_id, account_id if holds_money else None,
                refund=holds_money, goal_uid=goal_uid or None,
            )

        self._mutate(work)


class LoanController(_Mutating):
    resultChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._result: dict | None = None
        self._added = ""
        self.saved.connect(self._note_added)

    @Property(bool, notify=resultChanged)
    def hasResult(self):
        return self._result is not None

    @Property(str, notify=resultChanged)
    def monthlyText(self):
        return f"{format_amount(self._result['monthly_payment'])} ₺" if self._result else "—"

    @Property(str, notify=resultChanged)
    def totalText(self):
        return f"{format_amount(self._result['total_repayment'])} ₺" if self._result else "—"

    @Property(str, notify=resultChanged)
    def costText(self):
        return f"{format_amount(self._result['total_cost'])} ₺" if self._result else "—"

    @Property("QVariantList", notify=resultChanged)
    def schedule(self):
        if not self._result:
            return []
        return [
            {
                "month": row["month"],
                "payment": format_amount(row["payment"]),
                "principal": format_amount(row["principal"]),
                "interest": format_amount(row["interest"]),
                "balance": format_amount(row["balance"]),
            }
            for row in self._result["schedule"]
        ]

    @Property(str, notify=resultChanged)
    def addedNote(self):
        return self._added

    @Slot(str, str, str, bool)
    def calculate(self, amount_text, rate_text, months_text, include_taxes):
        from app.accounts import user_message
        from services.loan_service import MAX_MONTHS, calculate_loan

        self._added = ""
        try:
            rate_clean = (rate_text or "").strip().replace(",", ".")
            try:
                rate = float(rate_clean)
            except ValueError:
                raise FormError("Enter the monthly interest rate, for example 3,49.") from None
            self._result = calculate_loan(
                read_amount(amount_text, "loan amount"), rate,
                read_count(months_text, "number of months", 1, MAX_MONTHS),
                include_taxes,
            )
            self._set_message("")
        except ValueError as error:
            self._result = None
            self._set_message(user_message(error))
        self.resultChanged.emit()

    @Slot(str)
    def addToDebts(self, name):
        result = self._result
        if result is None:
            return

        def work():
            from services.debt_payment_service import DebtPaymentService

            if not (name or "").strip():
                raise FormError("Enter a name for the debt.")
            DebtPaymentService.create_debt(
                name.strip(), result["monthly_payment"], result["months"]
            )

        self._mutate(work)

    def _note_added(self) -> None:
        self._added = "Added to your debts."
        self.resultChanged.emit()

    @Slot()
    def clear(self):
        self._result = None
        self._added = ""
        self._set_message("")
        self.resultChanged.emit()
