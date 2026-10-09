"""Controller for the search box on the overview."""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.controllers import display_title, short_date
from services.background_task_manager import BackgroundTaskManager
from ui.i18n import tr
from utils.logging_config import get_logger

MAX_RESULTS = 12
_KIND_LABELS = {"account": "Account", "category": "Category", "transaction": "Transaction"}


class SearchController(QObject):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(parent)
        self._tasks = tasks
        self._query = ""
        self._results: list[dict] = []
        self._searching = False

    @Property("QVariantList", notify=changed)
    def results(self):
        return self._results

    @Property(bool, notify=changed)
    def active(self):
        """True while there is a query, whether or not anything matched."""
        return bool(self._query)

    @Property(bool, notify=changed)
    def searching(self):
        return self._searching

    @Slot(str)
    def search(self, text):
        query = (text or "").strip()
        if query == self._query:
            return
        self._query = query
        if not query:
            self._results, self._searching = [], False
            self.changed.emit()
            return
        self._searching = True
        self.changed.emit()

        def work():
            from services.search_service import search

            return query, search(query, limit=MAX_RESULTS, category_label=tr)

        def done(result):
            found_for, rows = result
            if found_for != self._query:
                return
            self._results = [self._view(row) for row in rows]
            self._searching = False
            self.changed.emit()

        def failed(error):
            get_logger().exception(
                "Arama başarısız.", exc_info=(type(error), error, error.__traceback__),
            )
            self._results, self._searching = [], False
            self.changed.emit()

        # Each keystroke replaces the search before it, so only the latest runs on.
        self._tasks.submit(
            "search", lambda _cancel: work(),
            on_success=done, on_error=failed, replace=True,
        )

    @Slot()
    def clear(self):
        self.search("")

    @staticmethod
    def _view(row: dict) -> dict:
        kind = row["kind"]
        if kind == "transaction":
            title = display_title(row["name"])
            detail = tr(row.get("detail") or "")
            date = str(row.get("date") or "")[:10]
            if date:
                detail = f"{short_date(date)} {date[:4]}  ·  {detail}" if detail else short_date(date)
            target, argument = "calendar", date
        elif kind == "account":
            # The account's name is the user's own text and is shown as typed.
            title = row["name"]
            detail = "Credit card" if row.get("detail") == "credit_card" else "Cash or checking"
            target, argument = "cards", ""
        else:
            # A category result carries the category itself in its name field:
            # a controlled value, translated like every other category label.
            category = row["name"]
            title = tr(category)
            detail = "Income category" if row.get("detail") == "income" else "Spending category"
            target, argument = "", ""
        return {
            "kind": _KIND_LABELS.get(kind, kind),
            "title": title,
            "detail": detail,
            "target": target,
            "argument": argument,
        }
