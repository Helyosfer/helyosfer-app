"""Controllers for the month-based tools: the budget plan and the calendar."""

from __future__ import annotations

import calendar
import datetime

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import read_amount
from app.payments import read_count
from app.controllers import display_title, format_amount
from app.payments import _Listing
from services.background_task_manager import BackgroundTaskManager
from ui.i18n import tr

_MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December")
_INCOME_TYPES = ("income", "Gelir")
_BLANK = {"day": 0, "count": 0, "today": False}


class _Monthly(_Listing):
    """A listing that shows one calendar month and can step between months."""

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        today = datetime.date.today()
        self._year, self._month = today.year, today.month

    def _step(self, delta: int) -> None:
        index = self._year * 12 + self._month - 1 + delta
        self._year, self._month = index // 12, index % 12 + 1
        self.refresh()

    def _title(self) -> str:
        return f"{_MONTH_NAMES[self._month - 1]} {self._year}"


class BudgetController(_Monthly):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._items: list[dict] = []
        self._progress: list[dict] = []
        self._summary = {"income": "—", "expense": "—", "reserved": "—", "left": "—",
                         "direction": 0}
        self._notice = ""

    @Property(str, notify=changed)
    def monthTitle(self):
        return self._title()

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @Property("QVariantList", notify=changed)
    def progress(self):
        return self._progress

    @Property(str, notify=changed)
    def incomeText(self):
        return self._summary["income"]

    @Property(str, notify=changed)
    def expenseText(self):
        return self._summary["expense"]

    @Property(str, notify=changed)
    def reservedText(self):
        return self._summary["reserved"]

    @Property(str, notify=changed)
    def leftText(self):
        return self._summary["left"]

    @Property(int, notify=changed)
    def leftDirection(self):
        return self._summary["direction"]

    @Property(str, notify=changed)
    def notice(self):
        return self._notice

    def _set_notice(self, text: str) -> None:
        self._notice = text
        self.changed.emit()

    @Slot()
    def previous(self):
        self._notice = ""
        self._step(-1)

    @Slot()
    def next(self):
        self._notice = ""
        self._step(1)

    def _fetch(self):
        from services import budget_service

        month, year = self._month, self._year
        progress = budget_service.get_category_budget_progress(month, year)
        for row in progress:
            # A carried-over category is measured against last month's leftover too.
            row["limit"] = (
                budget_service.get_effective_limit(row["category"], month, year)
                if row["rollover_enabled"] else row["planned"]
            )
        return (
            budget_service.calculate_monthly_budget(month, year),
            budget_service.get_effective_plan_items(month, year),
            progress,
        )

    def _show(self, data) -> None:
        summary, items, progress = data
        left = summary["remaining_budget"]
        self._summary = {
            "income": f"{format_amount(summary['planned_income'])} ₺",
            "expense": f"{format_amount(summary['planned_expense'])} ₺",
            "reserved": f"{format_amount(summary['reserved_recurring'])} ₺",
            "left": ("−" if left < 0 else "") + f"{format_amount(left)} ₺",
            "direction": (left > 0) - (left < 0),
        }
        ordered = sorted(items, key=lambda row: (row["type"] not in _INCOME_TYPES, row["id"]))
        self._items = [
            {
                "id": item["id"],
                "name": item["name"],
                "category": tr(item["category_name"]) if item["category_name"] else "",
                "income": item["type"] in _INCOME_TYPES,
                "amountText": f"{format_amount(float(item['amount']))} ₺",
                "amountForm": format_amount(float(item["amount"])),
                "everyMonth": bool(item["is_template"]),
                "kind": "income" if item["type"] in _INCOME_TYPES else "expense",
                "categoryKey": item["category_name"] or "",
                "rollover": bool(item.get("rollover_enabled")),
                "threshold": int(item.get("alert_threshold_pct") or 80),
            }
            for item in ordered
        ]
        self._progress = [self._progress_row(row) for row in progress]

    @staticmethod
    def _progress_row(row: dict) -> dict:
        limit = float(row["limit"])
        spent = float(row["actual"])
        left = limit - spent
        over = left < 0
        used = spent / limit * 100 if limit > 0 else (100.0 if spent > 0 else 0.0)
        near = not over and used >= row["alert_threshold_pct"]
        carried = limit - float(row["planned"])
        note = (
            f"{format_amount(-left)} ₺ over" if over else f"{format_amount(left)} ₺ left"
        )
        if abs(carried) >= 0.005:
            note += (
                f"  ·  {format_amount(abs(carried))} ₺ "
                + ("carried over" if carried > 0 else "overspent last month")
            )
        return {
            "category": tr(row["category"]),
            "spentText": f"{format_amount(spent)} ₺",
            "plannedText": f"{format_amount(limit)} ₺",
            "ratio": min(1.0, spent / limit) if limit > 0 else (1.0 if spent > 0 else 0.0),
            "over": over,
            "near": near,
            "note": note,
        }

    @Slot(str, str, str, str, bool)
    def addItem(self, kind, name, amount_text, category, every_month):
        self.saveItem(-1, kind, name, amount_text, category, every_month, False, "80")

    @Slot(int, str, str, str, str, bool, bool, str)
    def saveItem(self, item_id, kind, name, amount_text, category, every_month,
                 rollover, threshold_text):
        """Adds an item (`item_id` -1) or changes an existing one.

        Changing an item that repeats every month changes this month only:
        the service stores it as this month's own item, which takes the
        repeating one's place.
        """
        month, year = self._month, self._year
        was_repeating = any(
            item["id"] == item_id and item["everyMonth"] for item in self._items
        )

        def work():
            from services.budget_service import save_plan_item

            save_plan_item(
                item_type=kind, name=name,
                amount=read_amount(amount_text, "amount"),
                month=month, year=year,
                category=category or None,
                rollover_enabled=rollover and bool(category) and kind == "expense",
                is_template=every_month,
                alert_threshold_pct=read_count(
                    threshold_text or "80", "warning level", 1, 100
                ),
                item_id=item_id if item_id >= 0 else None,
                editing_a_template=was_repeating,
            )

        self._notice = ""
        self._mutate(work)

    @Slot(int)
    def deleteItem(self, item_id):
        from services.budget_service import delete_plan_item

        self._notice = ""
        self._mutate(lambda: delete_plan_item(item_id), announce=False)

    @Slot()
    def applyToYearEnd(self):
        """Copies this month's own items into the remaining months of the year."""
        if self._busy:
            return
        month, year = self._month, self._year
        self._set_busy(True)

        def work():
            from services.budget_service import apply_plan_to_year_end

            return apply_plan_to_year_end(month, year)

        def done(copied):
            self._set_busy(False)
            self._set_notice(
                f"Copied {copied} items to the rest of {year}." if copied
                else "The rest of the year already has these items."
            )

        def failed(error):
            self._set_busy(False)
            self._load_failed(error)

        self._tasks.submit(
            f"copy-{id(self)}", lambda _cancel: work(),
            on_success=done, on_error=failed, replace=False,
        )


class CalendarController(_Monthly):
    changed = Signal()
    dayChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._cells: list[dict] = []
        self._day = datetime.date.today().day
        self._day_items: list[dict] = []
        self._day_title = ""

    @Property(str, notify=changed)
    def monthTitle(self):
        return self._title()

    @Property("QVariantList", notify=changed)
    def cells(self):
        """Whole weeks of day cells, Monday first; a blank cell has day 0."""
        return self._cells

    @Property(int, notify=dayChanged)
    def selectedDay(self):
        return self._day

    @Property(str, notify=dayChanged)
    def dayTitle(self):
        return self._day_title

    @Property("QVariantList", notify=dayChanged)
    def dayItems(self):
        return self._day_items

    @Slot()
    def previous(self):
        self._day = 1
        self._step(-1)

    @Slot()
    def next(self):
        self._day = 1
        self._step(1)

    def _fetch(self):
        from services.calendar_service import get_month_transaction_days

        return self._year, self._month, get_month_transaction_days(self._year, self._month)

    def _show(self, data) -> None:
        year, month, counts = data
        today = datetime.date.today()
        first_weekday, days = calendar.monthrange(year, month)
        cells = [_BLANK] * first_weekday
        cells += [
            {
                "day": day,
                "count": counts.get(day, 0),
                "today": (year, month, day) == (today.year, today.month, today.day),
            }
            for day in range(1, days + 1)
        ]
        cells += [_BLANK] * (-len(cells) % 7)
        self._cells = cells
        self._day = min(self._day, days)
        self._load_day()

    @Slot(str)
    def showDate(self, iso_date):
        """Jumps to the month of 'YYYY-MM-DD' and selects that day."""
        try:
            day = datetime.date.fromisoformat((iso_date or "")[:10])
        except ValueError:
            return
        self._year, self._month, self._day = day.year, day.month, day.day
        self.refresh()

    @Slot(int)
    def selectDay(self, day):
        if day > 0:
            self._day = day
            self.dayChanged.emit()
            self._load_day()

    def _load_day(self) -> None:
        day = datetime.date(self._year, self._month, self._day)

        def fetch():
            from services.calendar_service import get_day_transactions

            return day, get_day_transactions(day)

        def loaded(result):
            loaded_day, items = result
            if loaded_day != datetime.date(self._year, self._month, self._day):
                return
            self._day_title = f"{loaded_day.day} {_MONTH_NAMES[loaded_day.month - 1]}"
            self._day_items = [
                {
                    "time": item["time"] or "",
                    "title": display_title(item["description"] or item["category"]),
                    "category": tr(item["category"] or ""),
                    "amount": ("+" if item["type"] == "income" else "−")
                    + format_amount(item["amount"]) + " ₺",
                    "income": item["type"] == "income",
                }
                for item in items
            ]
            self.dayChanged.emit()

        self._tasks.submit(
            f"day-{id(self)}", lambda _cancel: fetch(),
            on_success=loaded, on_error=self._load_failed, replace=True,
        )
