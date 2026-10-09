"""Controllers for the calculators: loan, deposit interest, growth, goal time."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, _Mutating, read_amount, user_message
from app.controllers import format_amount, short_date
from app.payments import read_count
from app.settings import local_path
from app.language import later, say
from services.background_task_manager import BackgroundTaskManager
from utils.logging_config import get_logger

LOAN_KINDS = (("consumer", later("Consumer (up to 36 months)")),
              ("vehicle", later("Vehicle (up to 48 months)")),
              ("housing", later("Housing (up to 120 months)")))
_UPFRONT_LABELS = {
    "allocation_fee": later("Allocation fee (with tax)"),
    "insurance": later("Life insurance (estimate)"),
}


def read_rate(text: str, label: str) -> float:
    cleaned = (text or "").strip().replace(",", ".").replace("%", "")
    try:
        value = float(cleaned)
    except ValueError:
        raise FormError(say("Enter the {0}, for example 3,49.", label)) from None
    if not 0 < value <= 1000:
        raise FormError(say("The {0} must be greater than 0.", label))
    return value


def money(value) -> str:
    return f"{format_amount(value)} ₺"


class LoanController(_Mutating):
    resultChanged = Signal()
    chargesChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._result: dict | None = None
        self._principal = 0.0
        self._charges: list[dict] = []
        self._note = ""
        self.saved.connect(self._note_added)

    # -- result --------------------------------------------------------------
    @Property(bool, notify=resultChanged)
    def hasResult(self):
        return self._result is not None

    def _money(self, key: str) -> str:
        return money(self._result[key]) if self._result else "—"

    @Property(str, notify=resultChanged)
    def monthlyText(self):
        return self._money("monthly_payment")

    @Property(str, notify=resultChanged)
    def totalText(self):
        return self._money("total_repayment")

    @Property(str, notify=resultChanged)
    def costText(self):
        return self._money("total_cost")

    @Property(str, notify=resultChanged)
    def netCashText(self):
        return self._money("net_cash")

    @Property(bool, notify=resultChanged)
    def hasDeductions(self):
        return bool(self._result and self._result["upfront"])

    @Property(bool, notify=resultChanged)
    def hasExtras(self):
        return bool(self._result and self._result["spread_total"] > 0)

    @Property("QVariantList", notify=resultChanged)
    def deductions(self):
        if not self._result:
            return []
        return [
            {"label": say(_UPFRONT_LABELS.get(item["name"], item["name"])),
             "value": money(item["amount"])}
            for item in self._result["upfront"]
        ]

    @Property("QVariantList", notify=resultChanged)
    def schedule(self):
        if not self._result:
            return []
        return [
            {
                "month": row["month"],
                "payment": format_amount(row["payment"]),
                "extra": format_amount(row["extra"]),
                "total": format_amount(row["total"]),
                "principal": format_amount(row["principal"]),
                "interest": format_amount(row["interest"]),
                "balance": format_amount(row["balance"]),
            }
            for row in self._result["schedule"]
        ]

    @Property(str, notify=resultChanged)
    def note(self):
        """The outcome of the last save or export."""
        return self._note

    def _set_note(self, text: str) -> None:
        self._note = text
        self.resultChanged.emit()

    # -- charges -------------------------------------------------------------
    @Property("QVariantList", constant=True)
    def kinds(self):
        return [{"key": key, "label": say(label)} for key, label in LOAN_KINDS]

    @Property("QVariantList", notify=chargesChanged)
    def charges(self):
        return [
            {
                "name": charge["name"],
                "detail": (
                    say("once, up front") if charge["kind"] == "upfront"
                    else say("spread over {0} months", charge['months'])
                ),
                "amount": money(charge["amount"]),
            }
            for charge in self._charges
        ]

    @Slot(str, str, bool, str)
    def addCharge(self, name, amount_text, spread, months_text):
        try:
            if not (name or "").strip():
                raise FormError(say("Enter a name for the charge."))
            charge = {
                "name": name.strip(),
                "amount": read_amount(amount_text, say("charge amount")),
                "kind": "spread" if spread else "upfront",
                "months": read_count(months_text, say("number of months"), 1, 360) if spread else 1,
            }
        except ValueError as error:
            self._set_message(user_message(error))
            return
        self._charges.append(charge)
        self._set_message("")
        self.chargesChanged.emit()

    @Slot(int)
    def removeCharge(self, index):
        if 0 <= index < len(self._charges):
            del self._charges[index]
            self.chargesChanged.emit()

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, bool, bool, str)
    def calculate(self, amount_text, rate_text, months_text, include_taxes, detailed, kind):
        from services.loan_service import MAX_MONTHS, calculate_loan

        self._note = ""
        try:
            principal = read_amount(amount_text, say("loan amount"))
            self._result = calculate_loan(
                principal,
                read_rate(rate_text, say("monthly interest rate")),
                read_count(months_text, say("number of months"), 1, MAX_MONTHS),
                include_taxes,
                loan_kind=(kind or None) if detailed else None,
                bank_fees=detailed,
                charges=self._charges if detailed else (),
            )
            self._principal = principal
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
                raise FormError(say("Enter a name for the debt."))
            DebtPaymentService.create_debt(
                name.strip(), result["monthly_payment"], result["months"]
            )

        self._mutate(work)

    def _note_added(self) -> None:
        self._set_note(say("Added to your debts."))

    @Slot(str)
    def exportPdf(self, url):
        result, principal = self._result, self._principal
        if result is None or self._busy:
            return
        self._set_busy(True)

        def work():
            from services.loan_report import write_loan_schedule_pdf

            return write_loan_schedule_pdf(local_path(url, ".pdf"), result, principal=principal)

        def done(path):
            import os

            self._set_busy(False)
            self._set_message("")
            self._set_note(say("Saved {0}.", os.path.basename(path)))

        def failed(error):
            self._set_busy(False)
            if not isinstance(error, (ValueError, OSError)):
                # Not a bad name or a folder that cannot be written: the
                # writer itself failed, and the reason must not be lost.
                get_logger().exception(
                    "PDF yazılamadı.", exc_info=(type(error), error, error.__traceback__),
                )
            self._set_message(
                user_message(error) if isinstance(error, ValueError)
                else say("The file could not be saved there. Choose another location.")
            )

        self._tasks.submit(
            f"pdf-{id(self)}", lambda _cancel: work(),
            on_success=done, on_error=failed, replace=False,
        )


class CalculatorController(_Mutating):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._interest: list[dict] = []
        self._growth: list[dict] = []
        self._growth_series: list[float] = []
        self._goal: list[dict] = []
        self._goal_plan: dict | None = None
        self._goal_note = ""
        self._answer = ""
        self.saved.connect(self._goal_created)

    @Property("QVariantList", notify=changed)
    def interestRows(self):
        return self._interest

    @Property("QVariantList", notify=changed)
    def growthRows(self):
        return self._growth

    @Property("QVariantList", notify=changed)
    def growthSeries(self):
        return self._growth_series

    @Property("QVariantList", notify=changed)
    def growthLabels(self):
        return [say("Year {0}", year) for year in range(len(self._growth_series))]

    @Property("QVariantList", notify=changed)
    def goalRows(self):
        return self._goal

    @Property(bool, notify=changed)
    def goalReady(self):
        return self._goal_plan is not None

    @Property(str, notify=changed)
    def goalNote(self):
        return self._goal_note

    @Property(str, notify=changed)
    def answer(self):
        return self._answer

    def _guard(self, action) -> bool:
        try:
            action()
        except ValueError as error:
            self._set_message(user_message(error))
            return False
        self._set_message("")
        return True

    @Slot(str, str, str)
    def interest(self, principal_text, rate_text, days_text):
        def action():
            from services.calculator_service import deposit_interest

            result = deposit_interest(
                read_amount(principal_text, say("deposit amount")),
                read_rate(rate_text, say("yearly interest rate")),
                read_count(days_text, say("number of days"), 1, 36500),
            )
            self._interest = [
                {"label": say("Interest after tax"), "value": "+" + money(result["net_interest"]), "tone": 1},
                {"label": say("At maturity"), "value": money(result["maturity_value"]), "tone": 0},
                {"label": say("Withholding tax (5 %)"), "value": money(result["tax"]), "tone": 0},
            ]

        if not self._guard(action):
            self._interest = []
        self.changed.emit()

    @Slot(str, str, str, str)
    def growth(self, principal_text, rate_text, years_text, deposit_text):
        def action():
            from services.calculator_service import compound_growth

            result = compound_growth(
                read_amount(principal_text, say("starting amount")),
                read_rate(rate_text, say("yearly return")),
                read_count(years_text, say("number of years"), 1, 100),
                read_amount(deposit_text, say("monthly contribution"), optional=True),
            )
            self._growth = [
                {"label": say("You put in"), "value": money(result["invested"]), "tone": 0},
                {"label": say("Growth"), "value": "+" + money(result["gain"]), "tone": 1},
                {"label": say("Final value"), "value": money(result["final_value"]), "tone": 0},
            ]
            self._growth_series = result["series"]

        if not self._guard(action):
            self._growth, self._growth_series = [], []
        self.changed.emit()

    @Slot(str, str, bool)
    def goalTime(self, target_text, deposit_text, daily):
        self._goal_note = ""

        def action():
            from services.calculator_service import DAILY, MONTHLY, time_to_goal

            target = read_amount(target_text, say("target amount"))
            result = time_to_goal(
                target, read_amount(deposit_text, say("regular amount")),
                DAILY if daily else MONTHLY,
            )
            reached = datetime.date.today() + datetime.timedelta(days=result["days"])
            count = result["deposits"]
            if daily:
                needed = say("1 day") if count == 1 else say("{0} days", count)
            else:
                needed = say("1 month") if count == 1 else say("{0} months", count)
            self._goal = [
                {"label": say("Time needed"), "value": needed, "tone": 0},
                {"label": say("Reached around"),
                 "value": f"{short_date(reached.isoformat())} {reached.year}", "tone": 0},
            ]
            self._goal_plan = {"target": target, "date": reached}

        if not self._guard(action):
            self._goal, self._goal_plan = [], None
        self.changed.emit()

    @Slot(str)
    def createGoal(self, name):
        plan = self._goal_plan
        if plan is None:
            return

        def work():
            from services.savings_service import SavingsService

            if not (name or "").strip():
                raise FormError(say("Enter a name for the goal."))
            target_date = plan["date"] if plan["date"] > datetime.date.today() else None
            SavingsService.create_goal(
                name.strip(), plan["target"],
                target_date.isoformat() if target_date else None,
            )

        self._mutate(work)

    def _goal_created(self) -> None:
        self._goal_note = say("Added to your savings goals.")
        self.changed.emit()

    @Slot(str)
    def evaluate(self, expression):
        from utils.calculator import evaluate_calculator_expression

        text = (expression or "").replace(",", ".").replace("×", "*").replace("÷", "/").replace("^", "**")
        try:
            value = evaluate_calculator_expression(text)
            if isinstance(value, complex) or value != value or value in (float("inf"), float("-inf")):
                raise ValueError
            shown = f"{value:,.10f}".rstrip("0").rstrip(".")
            self._answer = shown.replace(",", "X").replace(".", ",").replace("X", ".")
            self._set_message("")
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, TypeError):
            self._answer = ""
            self._set_message(say("This cannot be calculated. Check the expression."))
        self.changed.emit()
