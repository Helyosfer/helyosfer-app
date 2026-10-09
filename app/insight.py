"""Controllers for insights, what-if projections and past balances."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, _Mutating, user_message
from app.controllers import display_title, format_amount, format_signed, short_date
from app.payments import FREQUENCIES, _Listing, read_day
from services.background_task_manager import BackgroundTaskManager
from app.language import later, say, tr
from app.language import percent as written_percent

_SOURCE_LABELS = {
    "transaction": later("Transactions"),
    "account_opened": later("Opening balances"),
    "card_payment": later("Card payments"),
    "debt_payment": later("Debt payments"),
    "savings_deposit": later("Moved into savings goals"),
    "savings_withdraw": later("Taken back from savings goals"),
    "savings_goal_created": later("Savings goals opened"),
    "asset_purchase": later("Asset purchases"),
    "asset_sale": later("Asset sales"),
}
HORIZONS = ((30, later("1 month")), (90, later("3 months")), (180, later("6 months")), (365, later("1 year")))


def percent(value: float) -> str:
    """A share between 0 and 1 as a percentage."""
    return written_percent(value * 100)


def read_percent(text: str, label: str) -> float:
    cleaned = (text or "").strip().replace(",", ".").replace("%", "")
    if not cleaned:
        return 0.0
    try:
        value = float(cleaned)
    except ValueError:
        raise FormError(say("Enter the {0} as a percentage, for example 10 or -5.", label)) from None
    if not -100 <= value <= 1000:
        raise FormError(say("The {0} must be between -100 and 1000.", label))
    return value


def read_signed_amount(text: str) -> float:
    """'5.000' or '-2.500,50' -> float; empty is 0."""
    from utils.formatters import parse_amount

    cleaned = (text or "").strip()
    if not cleaned:
        return 0.0
    negative = cleaned.startswith(("-", "−"))
    try:
        value = parse_amount(cleaned.lstrip("-−+ "))
    except ValueError:
        raise FormError(say("Enter a valid one-time amount, for example 5.000 or -2.500.")) from None
    return -value if negative else value


class InsightsController(_Listing):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._health = {"score": "", "label": "", "ready": False, "rows": [], "note": ""}
        self._forecast = {"ready": False, "balance": "", "change": "", "direction": 0, "note": ""}
        self._anomalies: list[dict] = []
        self._candidates: list[dict] = []

    @Property(bool, notify=changed)
    def healthReady(self):
        return self._health["ready"]

    @Property(str, notify=changed)
    def score(self):
        return self._health["score"]

    @Property(str, notify=changed)
    def scoreLabel(self):
        return self._health["label"]

    @Property(float, notify=changed)
    def scoreRatio(self):
        return self._health.get("ratio", 0.0)

    @Property("QVariantList", notify=changed)
    def healthRows(self):
        return self._health["rows"]

    @Property(str, notify=changed)
    def healthNote(self):
        return self._health["note"]

    @Property(bool, notify=changed)
    def forecastReady(self):
        return self._forecast["ready"]

    @Property(str, notify=changed)
    def forecastBalance(self):
        return self._forecast["balance"]

    @Property(str, notify=changed)
    def forecastChange(self):
        return self._forecast["change"]

    @Property(int, notify=changed)
    def forecastDirection(self):
        return self._forecast["direction"]

    @Property(str, notify=changed)
    def forecastNote(self):
        return self._forecast["note"]

    @Property("QVariantList", notify=changed)
    def anomalies(self):
        return self._anomalies

    @Property("QVariantList", notify=changed)
    def candidates(self):
        return self._candidates

    @staticmethod
    def _fetch():
        from services import insights_service

        return (
            insights_service.compute_financial_health_score(),
            insights_service.generate_monthly_forecast(),
            insights_service.detect_anomalies(),
            insights_service.detect_recurring_candidates(),
        )

    def _show(self, data) -> None:
        from services.insights_service import score_label

        health, forecast, anomalies, candidates = data
        if health.get("insufficient_data"):
            self._health = {
                "score": "", "label": "", "ready": False, "rows": [], "ratio": 0.0,
                "note": say("Not enough income and spending recorded yet to score your finances."),
            }
        else:
            parts = health["breakdown"]
            self._health = {
                "score": f"{health['score']:.0f}",
                "label": tr(score_label(health["score"])),
                "ratio": max(0.0, min(1.0, health["score"] / 100)),
                "ready": True,
                "note": say("Based on the last {0} days.", parts['lookback_days']),
                "rows": [
                    {"label": say("Savings rate"), "value": percent(parts["savings_rate"]),
                     "points": f"{parts['savings_score']:.0f} / 100", "weight": say("half of the score")},
                    {"label": say("Debt payments to income"), "value": percent(parts["debt_ratio"]),
                     "points": f"{parts['debt_score']:.0f} / 100", "weight": say("30 % of the score")},
                    {"label": say("Spending volatility"), "value": percent(parts["expense_volatility"]),
                     "points": f"{parts['volatility_score']:.0f} / 100", "weight": say("20 % of the score")},
                ],
            }

        if forecast.get("insufficient_data"):
            self._forecast = {
                "ready": False, "balance": "", "change": "", "direction": 0,
                "note": (
                    say("A month-end forecast needs about three months of history; {0} days are recorded so far.", forecast.get('days_available', 0))
                ),
            }
        else:
            surplus = forecast["projected_surplus"]
            self._forecast = {
                "ready": True,
                "balance": f"{format_amount(forecast['projected_month_end_balance'])} ₺",
                "change": format_signed(surplus) + say(" from today"),
                "direction": (surplus > 0) - (surplus < 0),
                "note": (
                    say("{0} days left in the month, at your average daily income and spending.", forecast['days_remaining'])
                ),
            }

        self._anomalies = [
            {
                "id": item["id"],
                "title": display_title(item["description"] or item["category"]),
                "category": tr(item["category"]),
                "date": short_date(item["date"]),
                "amount": f"{format_amount(item['amount'])} ₺",
                "note": (
                    say("{0} ₺ above the usual {1} ₺", format_amount(item['deviation']), format_amount(item['category_mean']))
                ),
            }
            for item in anomalies
        ]
        frequency_labels = dict(FREQUENCIES)
        self._candidates = [
            {
                "key": item["key"],
                "name": item["name"],
                "category": tr(item["category"]),
                "amount": f"{format_amount(item['average_amount'])} ₺",
                "frequency": say(frequency_labels.get(item["frequency"], later("Irregular"))),
                "seen": say("seen {0} times", item['occurrences']),
                "monthly": say("{0} ₺ a month", format_amount(item['monthly_cost'])),
                "canTrack": bool(item.get("can_track")),
            }
            for item in candidates
        ]

    @Slot(int)
    def dismissAnomaly(self, transaction_id):
        from services.insights_service import dismiss_anomaly

        self._mutate(lambda: dismiss_anomaly(transaction_id), announce=False)

    @Slot(str)
    def dismissCandidate(self, key):
        from services.insights_service import dismiss_recurring_candidate

        self._mutate(lambda: dismiss_recurring_candidate(key), announce=False)

    @Slot(str, int)
    def trackCandidate(self, key, account_id):
        """Starts tracking a detected pattern as a manual recurring payment."""
        def work():
            from database.db import insert_recurring_payment
            from services.insights_service import detect_recurring_candidates

            if account_id < 0:
                raise FormError(say("Add an account first."))
            candidate = next(
                (c for c in detect_recurring_candidates() if c["key"] == key), None
            )
            if candidate is None or not candidate.get("can_track"):
                raise FormError(say("This pattern is no longer detected."))
            due = candidate.get("next_due_date") or datetime.date.today().isoformat()
            insert_recurring_payment(
                candidate["name"], candidate["average_amount"], candidate["category"],
                candidate["frequency"], due, False, account_id=account_id,
            )

        self._mutate(work)


class ScenarioController(_Mutating):
    resultChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._result: dict | None = None

    @Property("QVariantList", constant=True)
    def horizons(self):
        return [{"key": str(days), "label": say(label)} for days, label in HORIZONS]

    @Property(bool, notify=resultChanged)
    def hasResult(self):
        return self._result is not None

    def _text(self, key: str) -> str:
        return self._result[key] if self._result else ""

    @Property(str, notify=resultChanged)
    def baseText(self):
        return self._text("base")

    @Property(str, notify=resultChanged)
    def scenarioText(self):
        return self._text("scenario")

    @Property(str, notify=resultChanged)
    def differenceText(self):
        return self._text("difference")

    @Property(int, notify=resultChanged)
    def differenceDirection(self):
        return self._result["direction"] if self._result else 0

    @Property(str, notify=resultChanged)
    def note(self):
        return self._text("note")

    @Property(bool, notify=resultChanged)
    def goesNegative(self):
        return bool(self._result and self._result["negative"])

    @Property("QVariantList", notify=resultChanged)
    def baseSeries(self):
        return self._result["base_series"] if self._result else []

    @Property("QVariantList", notify=resultChanged)
    def scenarioSeries(self):
        return self._result["scenario_series"] if self._result else []

    @Property("QVariantList", notify=resultChanged)
    def labels(self):
        return self._result["labels"] if self._result else []

    @Slot(str, str, str, str)
    def run(self, income_text, expense_text, one_time_text, horizon):
        if self._busy:
            return
        try:
            income_pct = read_percent(income_text, say("income change"))
            expense_pct = read_percent(expense_text, say("spending change"))
            one_time = read_signed_amount(one_time_text)
            days = int(horizon or 90)
        except ValueError as error:
            self._set_message(user_message(error))
            return
        self._set_busy(True)

        def work():
            from services.dashboard_service import compute_dashboard_metrics
            from services.projection_service import simulate_scenario

            metrics = compute_dashboard_metrics()
            return simulate_scenario(
                metrics["total_balance"],
                metrics["projection_daily_income"],
                metrics["projection_daily_expense"],
                income_delta_pct=income_pct, expense_delta_pct=expense_pct,
                days=days, one_time_adjustment=one_time,
            )

        def done(result):
            self._set_busy(False)
            self._set_message("")
            today = datetime.date.today()
            step = max(1, result["days"] // 30)
            picked = list(range(0, result["days"] + 1, step))
            if picked[-1] != result["days"]:
                picked.append(result["days"])
            inputs = result["inputs"]
            difference = result["difference"]
            self._result = {
                "base": f"{format_amount(result['base_final'])} ₺",
                "scenario": f"{format_amount(result['scenario_final'])} ₺",
                "difference": format_signed(difference),
                "direction": (difference > 0) - (difference < 0),
                "negative": result["goes_negative"],
                "base_series": [result["base_series"][day][1] for day in picked],
                "scenario_series": [result["scenario_series"][day][1] for day in picked],
                "labels": [
                    short_date((today + datetime.timedelta(days=day)).isoformat())
                    for day in picked
                ],
                "note": (
                    say("Based on your last 30 days: about {0} ₺ in and {1} ₺ out a month.", format_amount(inputs['base_daily_income'] * 30), format_amount(inputs['base_daily_expense'] * 30))
                ),
            }
            self.resultChanged.emit()

        def failed(error):
            self._set_busy(False)
            self._set_message(user_message(error))

        self._tasks.submit(
            f"scenario-{id(self)}", lambda _cancel: work(),
            on_success=done, on_error=failed, replace=True,
        )


class HistoryController(_Mutating):
    resultChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._result: dict | None = None

    @Property(bool, notify=resultChanged)
    def hasResult(self):
        return self._result is not None

    def _text(self, key: str) -> str:
        return self._result[key] if self._result else ""

    @Property(str, notify=resultChanged)
    def title(self):
        return self._text("title")

    @Property(str, notify=resultChanged)
    def balanceText(self):
        return self._text("balance")

    @Property(str, notify=resultChanged)
    def savingsText(self):
        return self._text("savings")

    @Property(str, notify=resultChanged)
    def changeText(self):
        return self._text("change")

    @Property(int, notify=resultChanged)
    def changeDirection(self):
        return self._result["direction"] if self._result else 0

    @Property("QVariantList", notify=resultChanged)
    def sources(self):
        return self._result["sources"] if self._result else []

    @Slot(str)
    def lookUp(self, date_text):
        if self._busy:
            return
        try:
            day = read_day(date_text)
            if day > datetime.date.today():
                raise FormError(say("Choose today or an earlier date."))
        except ValueError as error:
            self._set_message(user_message(error))
            return
        self._set_busy(True)

        def work():
            from services.history_service import diff_between, get_balance_at

            return day, get_balance_at(day.isoformat()), diff_between(
                day.isoformat(), datetime.date.today().isoformat()
            )

        def done(data):
            loaded_day, balance, diff = data
            self._set_busy(False)
            if balance["total_balance"] is None:
                self._result = None
                self._set_message(
                    say("There are no records that far back. Balances are known from "
                    "the day your first account was added.")
                )
                self.resultChanged.emit()
                return
            self._set_message("")
            change = diff["balance_change"]
            self._result = {
                "title": f"{short_date(loaded_day.isoformat())} {loaded_day.year}",
                "balance": f"{format_amount(balance['total_balance'])} ₺",
                "savings": f"{format_amount(balance['savings_total'] or 0)} ₺",
                "change": format_signed(change) + say(" since then") if change is not None else "",
                "direction": ((change > 0) - (change < 0)) if change is not None else 0,
                "sources": [
                    {
                        "label": say(_SOURCE_LABELS.get(
                            source, source.replace("_", " ").capitalize()
                        )),
                        "count": say("{0} entries", bucket['count']) if bucket["count"] != 1 else say("1 entry"),
                        "amount": format_signed(bucket["delta"]),
                        "positive": bucket["delta"] >= 0,
                    }
                    for source, bucket in sorted(
                        diff["by_source"].items(), key=lambda pair: -abs(pair[1]["delta"])
                    )
                ],
            }
            self.resultChanged.emit()

        def failed(error):
            self._set_busy(False)
            self._set_message(user_message(error))

        self._tasks.submit(
            f"history-{id(self)}", lambda _cancel: work(),
            on_success=done, on_error=failed, replace=True,
        )
