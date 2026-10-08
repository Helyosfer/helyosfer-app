"""Objects the QML views bind to.

A controller holds display-ready state and forwards user actions to services.
It never computes a financial figure itself and never touches the database on
the interface thread: work is submitted to the background task manager and
the result comes back through `Dispatcher` on the interface thread.
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal

from PySide6.QtCore import Property, QObject, Signal, Slot

from services import auth_service
from services.background_task_manager import BackgroundTaskManager
from ui.i18n import tr
from utils.errors import FinancialDataIntegrityError
from utils.logging_config import get_logger, log_integrity_error
from utils.version import APP_VERSION

PERIODS = (
    ("Bugün", "Today"),
    ("1 Hafta", "1W"),
    ("1 Ay", "1M"),
    ("1 Yıl", "1Y"),
)
_PERIOD_PHRASES = {
    "Bugün": "today",
    "1 Hafta": "past week",
    "1 Ay": "past month",
    "1 Yıl": "past year",
}
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_amount(value) -> str:
    """1234.5 -> '1.234,50' (Turkish grouping, no currency sign)."""
    text = f"{abs(Decimal(value)):,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def format_signed(value) -> str:
    sign = "−" if value < 0 else "+"
    return f"{sign}{format_amount(value)} ₺"


def short_date(text: str) -> str:
    """'2026-10-08 ...' or '08/10/2026' -> '08 Oct'; anything else unchanged."""
    head = (text or "")[:10]
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            day = datetime.datetime.strptime(head, pattern).date()
        except ValueError:
            continue
        return f"{day.day:02d} {_MONTHS[day.month - 1]}"
    return text or ""


# Descriptions the services generate are stored in Turkish. They are data, so
# they are recognised by shape and reworded for display; the user's own part
# (a name) is carried over untouched and never passes through the catalog.
_GENERATED_SUFFIXES = (
    (" Borç Ödemesi", " debt payment"),
    (" (Otomatik Taksit Ödemesi)", " (automatic installment)"),
    (" (Tamamen Kapatma)", " (paid off)"),
    (" (Otomatik)", " (automatic)"),
)
_INSTALLMENTS = re.compile(r" \((\d+) Taksit Ödemesi\)$")
_ASSET_TRADE = re.compile(r"^(.*) \((.+)\) (alındı|satıldı) — ([\d.,]+) adet\b")
_GOLD_LABELS = {
    "Gram Altın": "Gram gold", "Çeyrek Altın": "Quarter gold coin",
    "Yarım Altın": "Half gold coin", "Tam Altın": "Full gold coin",
    "Ons Altın": "Ounce of gold",
}


def display_title(text: str) -> str:
    """Stored descriptions as shown: generated ones are put into English."""
    for suffix, replacement in _GENERATED_SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)] + replacement
    match = _INSTALLMENTS.search(text)
    if match:
        count = int(match.group(1))
        noun = "installment" if count == 1 else "installments"
        return f"{text[: match.start()]} ({count} {noun})"
    match = _ASSET_TRADE.match(text)
    if match:
        name, code, verb, quantity = match.groups()
        quantity = quantity.rstrip("0").rstrip(".") if "." in quantity else quantity
        action = "Bought" if verb == "alındı" else "Sold"
        return f"{action} {quantity.replace('.', ',')} × {_GOLD_LABELS.get(name, name)} ({code})"
    return tr(text)


class Dispatcher(QObject):
    """Runs a callable on the interface thread, from any thread."""

    _posted = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._posted.connect(self._run)

    def post(self, callback) -> None:
        self._posted.emit(callback)

    @Slot(object)
    def _run(self, callback) -> None:
        callback()


class AppController(QObject):
    screenChanged = Signal()
    darkChanged = Signal()
    failureChanged = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self._store = store
        self._screen = ""
        self._dark = True
        self._failure_title = ""
        self._failure_message = ""
        self._failure_note = ""
        if store is not None:
            self._dark = store.get("display").get("style", "Dark") != "Light"

    @Property(str, notify=screenChanged)
    def screen(self):
        return self._screen

    def show(self, screen: str) -> None:
        if screen != self._screen:
            self._screen = screen
            self.screenChanged.emit()

    @Property(bool, notify=darkChanged)
    def dark(self):
        return self._dark

    @Slot()
    def toggleTheme(self):
        self._dark = not self._dark
        self._store.put("display", style="Dark" if self._dark else "Light")
        self.darkChanged.emit()

    @Property(str, constant=True)
    def version(self):
        return APP_VERSION

    @Property(str, notify=failureChanged)
    def failureTitle(self):
        return self._failure_title

    @Property(str, notify=failureChanged)
    def failureMessage(self):
        return self._failure_message

    @Property(str, notify=failureChanged)
    def failureNote(self):
        return self._failure_note

    def fail(self, title: str, message: str) -> None:
        """Fail-closed startup surface: only fixed, safe text reaches the user."""
        self.halt(
            tr(title), tr(message),
            "Nothing was changed. Close this window when you are ready.",
        )

    def halt(self, title: str, message: str, note: str = "") -> None:
        """Replaces the application with a notice that can only be closed."""
        self._failure_title = title
        self._failure_message = message
        self._failure_note = note
        self.failureChanged.emit()
        self.show("failure")


class AuthController(QObject):
    messageChanged = Signal()
    busyChanged = Signal()
    signedIn = Signal()
    rejected = Signal()

    def __init__(self, app: AppController, auth, tasks: BackgroundTaskManager, parent=None):
        super().__init__(parent)
        self._app = app
        self._auth = auth
        self._tasks = tasks
        self._message = ""
        self._busy = False

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    def _set_message(self, text: str) -> None:
        if text != self._message:
            self._message = text
            self.messageChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def start(self) -> None:
        self._app.show(self._auth.start_screen())

    def _submit(self, work) -> None:
        # Argon2 verification is deliberately slow; keep it off the interface thread.
        if self._busy:
            return
        self._set_busy(True)
        self._tasks.submit(
            "auth",
            lambda _cancel: work(),
            on_success=self._finish,
            on_error=self._crashed,
            replace=False,
        )

    def _finish(self, result) -> None:
        self._set_busy(False)
        self._set_message(result.message)
        if not result.ok:
            self.rejected.emit()
        self._app.show(result.screen)
        if result.ok and result.screen == auth_service.HOME:
            self.signedIn.emit()

    def _crashed(self, error) -> None:
        self._set_busy(False)
        get_logger().exception(
            "Oturum işlemi başarısız.",
            exc_info=(type(error), error, error.__traceback__),
        )
        self._set_message("Something went wrong. Try again.")
        self.rejected.emit()

    @Slot(str)
    def login(self, password):
        self._submit(lambda: self._auth.login(password))

    @Slot(str, str)
    def setup(self, password, confirmation):
        self._submit(lambda: self._auth.setup(password, confirmation))

    @Slot(str, str)
    def createFirstAccount(self, name, balance_text):
        from services.account_service import CHECKING, AccountService
        from utils.formatters import parse_amount_to_float

        text = (balance_text or "").strip()
        try:
            balance = parse_amount_to_float(text, default=None) if text else 0.0
            if balance is None:
                raise ValueError
            AccountService.create_account(
                name=name, account_type=CHECKING, initial_balance=balance,
            )
        except ValueError as exc:
            self._set_message(tr(str(exc)) or tr("Geçerli bir tutar girin!"))
            self.rejected.emit()
            return
        self._set_message("")
        self._app.show(auth_service.HOME)
        self.signedIn.emit()

    @Slot()
    def logout(self):
        self._set_message("")
        self._app.show(self._auth.start_screen())

    @Slot()
    def clearMessage(self):
        self._set_message("")


class DashboardController(QObject):
    changed = Signal()
    periodChanged = Signal()
    loadingChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(parent)
        self._tasks = tasks
        self._period = "1 Ay"
        self._loading = False
        self._state = self._empty_state()

    @staticmethod
    def _empty_state() -> dict:
        return {
            "whole": "—", "fraction": "", "change": "", "direction": 0,
            "income": "—", "expense": "—", "net": "—", "net_direction": 0,
            "series": [], "series_labels": [], "axis": [],
            "recent": [], "error": "",
        }

    # -- properties ----------------------------------------------------------
    @Property("QVariantList", constant=True)
    def periods(self):
        return [{"key": key, "label": label} for key, label in PERIODS]

    @Property(str, notify=periodChanged)
    def period(self):
        return self._period

    @Property(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    @Property(str, notify=changed)
    def balanceWhole(self):
        return self._state["whole"]

    @Property(str, notify=changed)
    def balanceFraction(self):
        return self._state["fraction"]

    @Property(str, notify=changed)
    def changeText(self):
        return self._state["change"]

    @Property(int, notify=changed)
    def changeDirection(self):
        return self._state["direction"]

    @Property(str, notify=changed)
    def incomeText(self):
        return self._state["income"]

    @Property(str, notify=changed)
    def expenseText(self):
        return self._state["expense"]

    @Property(str, notify=changed)
    def netText(self):
        return self._state["net"]

    @Property(int, notify=changed)
    def netDirection(self):
        return self._state["net_direction"]

    @Property("QVariantList", notify=changed)
    def series(self):
        return self._state["series"]

    @Property("QVariantList", notify=changed)
    def seriesLabels(self):
        return self._state["series_labels"]

    @Property("QVariantList", notify=changed)
    def recent(self):
        return self._state["recent"]

    @Property(str, notify=changed)
    def error(self):
        return self._state["error"]

    # -- actions -------------------------------------------------------------
    @Slot(str)
    def setPeriod(self, key):
        if key != self._period and key in dict(PERIODS):
            self._period = key
            self.periodChanged.emit()
            self.refresh()

    @Slot()
    def refresh(self):
        period = self._period
        self._loading = True
        self.loadingChanged.emit()
        self._tasks.submit(
            "dashboard",
            lambda _cancel: self._load(period),
            on_success=self._apply,
            on_error=self._failed,
            replace=True,
        )

    @staticmethod
    def _load(period: str) -> dict:
        from services import dashboard_service

        metrics = dashboard_service.compute_dashboard_metrics(period)
        return {
            "period": period,
            "metrics": metrics,
            "recent": dashboard_service.recent_transactions(8),
            "series": dashboard_service.balance_series(period),
        }

    def _apply(self, data: dict) -> None:
        metrics = data["metrics"]
        whole, _, fraction = format_amount(metrics["total_balance"]).partition(",")
        negative = metrics["total_balance"] < 0

        change = metrics["balance_change"]
        rate = metrics["change_rate"]
        label = _PERIOD_PHRASES[data["period"]]
        if change is None:
            change_text, direction = "No history for this period yet", 0
        else:
            direction = (change > 0) - (change < 0)
            change_text = format_signed(change)
            if rate is not None:
                change_text += f"  ·  {'−' if rate < 0 else '+'}{abs(rate):.1f} %".replace(".", ",")
            change_text += f"  ·  {label}"

        net = metrics["period_net"]
        self._state = {
            "whole": ("−" if negative else "") + whole,
            "fraction": f",{fraction} ₺",
            "change": change_text,
            "direction": direction,
            "income": f"{format_amount(metrics['period_income'])} ₺",
            "expense": f"{format_amount(metrics['period_expense'])} ₺",
            "net": format_signed(net),
            "net_direction": (net > 0) - (net < 0),
            "series": [point["balance"] for point in data["series"]],
            "series_labels": [short_date(point["date"]) for point in data["series"]],
            "recent": [self._row(item) for item in data["recent"]],
            "error": "",
        }
        self._done()

    @staticmethod
    def _row(item: dict) -> dict:
        income = item["type"] == "income"
        if item["readable"]:
            amount = ("+" if income else "−") + format_amount(item["amount"]) + " ₺"
            title = display_title(item["description"] or item["category"])
        else:
            amount, title = "—", "Unreadable record"
        return {
            "date": short_date(item["date"]),
            "title": title,
            "category": tr(item["category"]),
            "amount": amount,
            "income": income,
            "readable": item["readable"],
        }

    def _failed(self, error) -> None:
        state = self._empty_state()
        if isinstance(error, FinancialDataIntegrityError):
            error_id = log_integrity_error(error)
            state["error"] = (
                tr("Bazı kayıtlar okunamadığı için gösterilemiyor")
                + f" (Error: {error_id})"
            )
        else:
            get_logger().exception(
                "Dashboard görevi başarısız.",
                exc_info=(type(error), error, error.__traceback__),
            )
            state["error"] = "The overview could not be loaded."
        self._state = state
        self._done()

    def _done(self) -> None:
        self._loading = False
        self.loadingChanged.emit()
        self.changed.emit()
