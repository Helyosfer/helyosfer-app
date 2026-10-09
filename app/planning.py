"""Controllers for savings goals and the planning tools."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Property, Signal, Slot

from app.accounts import FormError, read_amount
from app.controllers import format_amount, short_date
from app.language import percent, say, tr
from app.payments import _Listing, read_day
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
        from services.account_service import AccountService
        from services.savings_auto_service import get_contributions
        from services.savings_service import SavingsService

        names = {account["id"]: account["name"] for account in AccountService.get_accounts()}
        return SavingsService.get_goals(), get_contributions(), names

    def _show(self, data) -> None:
        goals, plans, account_names = data
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
                    due = say("by {0} {1}", short_date(day.isoformat()), day.year)
                    months = months_between(today, day)
                    if not done and months > 0:
                        pace = say("{0} ₺ a month reaches it in time", format_amount(remaining / months))
                    elif not done:
                        pace = say("The target date has passed")
            views.append({
                "id": goal["id"],
                "uid": goal["goal_uid"] or "",
                "name": goal["goal_name"],
                "savedText": f"{format_amount(current)} ₺",
                "targetText": f"{format_amount(wanted)} ₺",
                "remainingText": f"{format_amount(remaining)} ₺",
                "progress": min(1.0, current / wanted) if wanted > 0 else 0.0,
                "percent": percent(min(100.0, current / wanted * 100)) if wanted > 0 else "",
                "due": due,
                "pace": pace,
                "done": done,
                "hasMoney": current > 0,
                **self._auto(plans.get(goal["goal_uid"]), account_names, done),
            })
        self._goals = views
        self._saved = f"{format_amount(saved)} ₺"
        self._target = f"{format_amount(target)} ₺"

    @staticmethod
    def _auto(plan, account_names, done) -> dict:
        """What a goal's card and its dialog need about its monthly contribution."""
        if not plan or done:
            return {"auto": False, "autoText": "", "autoAmountText": "", "autoDay": 0,
                    "autoAccount": -1}
        # The account's name is the user's own text and goes in as a value.
        return {
            "auto": True,
            "autoText": say(
                "{0} ₺ on day {1} of each month, from {2}",
                format_amount(plan["amount"]), plan["day"],
                account_names.get(plan["account_id"], "—"),
            ),
            "autoAmountText": format_amount(plan["amount"]),
            "autoDay": plan["day"],
            "autoAccount": plan["account_id"],
        }

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, int)
    def setAuto(self, goal_uid, amount_text, day_text, account_id):
        """Sets or changes the goal's monthly contribution."""
        def work():
            from app.payments import read_count
            from services.savings_auto_service import set_contribution

            amount = read_amount(amount_text, say("amount"))
            day = read_count(day_text, say("day of the month"), 1, 31)
            if account_id < 0:
                raise FormError(say("Choose an account."))
            set_contribution(goal_uid, account_id, amount, day)

        self._mutate(work)

    @Slot(str)
    def clearAuto(self, goal_uid):
        from services.savings_auto_service import clear_contribution

        self._mutate(lambda: clear_contribution(goal_uid))

    @Slot(str, str, str)
    def addGoal(self, name, target_text, date_text):
        def work():
            from services.savings_service import SavingsService

            if not (name or "").strip():
                raise FormError(say("Enter a name for the goal."))
            target_date = None
            if (date_text or "").strip():
                day = read_day(date_text)
                if day <= datetime.date.today():
                    raise FormError(say("Choose a target date after today."))
                target_date = day.isoformat()
            SavingsService.create_goal(
                name.strip(), read_amount(target_text, say("target amount")), target_date
            )

        self._mutate(work)

    @Slot(int, str, str, int, bool)
    def move(self, goal_id, goal_uid, amount_text, account_id, deposit):
        """Moves money into the goal (`deposit`) or back out of it."""
        def work():
            from services.savings_service import SavingsService

            if account_id < 0:
                raise FormError(say("Choose an account."))
            amount = read_amount(amount_text, say("amount"))
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
                raise FormError(say("Choose the account that receives the saved money."))
            SavingsService.delete_goal(
                goal_id, account_id if holds_money else None,
                refund=holds_money, goal_uid=goal_uid or None,
            )

        self._mutate(work)


class CategoriesController(_Listing):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._items: list[dict] = []

    @Property("QVariantList", notify=changed)
    def items(self):
        return self._items

    @staticmethod
    def _fetch():
        from services.queries import list_categories

        return list_categories()

    def _show(self, rows) -> None:
        self._items = sorted(
            (
                {
                    "key": row["category"],
                    # Built-in categories are catalog values; one the user
                    # added is not in the catalog and comes back as typed.
                    "name": tr(row["category"]),
                    "kind": row["type"],
                    "essential": row["importance"] == "main",
                    "custom": row["custom"],
                    "editable": not row["protected"],
                    "inUse": row["in_use"],
                }
                for row in rows
            ),
            # The user's own categories lead; they would otherwise be lost
            # among fifty.
            key=lambda item: (not item["custom"], item["name"].casefold()),
        )

    def _refuse_a_name_on_screen(self, name, but=None) -> None:
        """Refuses a name another category is already shown under.

        The service compares the names as stored. A built-in category is
        shown in the language of the interface, so a name can be free there
        and still be one the user already sees in the list.
        """
        from services.search_service import normalize

        wanted = normalize(" ".join(str(name or "").split()))
        if wanted and any(
            normalize(item["name"]) == wanted for item in self._items if item["key"] != but
        ):
            raise ValueError("Bu adda bir kategori zaten var.")

    @Slot(str, str, bool)
    def add(self, kind, name, essential):
        from services.queries import add_category

        def work():
            self._refuse_a_name_on_screen(name)
            add_category(name, kind, essential)

        self._mutate(work)

    @Slot(str, str)
    def rename(self, key, name):
        from services.queries import rename_category

        def work():
            self._refuse_a_name_on_screen(name, but=key)
            rename_category(key, name)

        self._mutate(work)

    @Slot(str)
    def remove(self, key):
        from services.queries import delete_category

        self._mutate(lambda: delete_category(key), announce=False)

    @Slot(str, str)
    def removeAndMove(self, key, target):
        """Removes a category in use; what is filed under it goes to `target`."""
        from services.queries import delete_category

        def work():
            if not target:
                raise FormError(say("Choose the category that takes over its records."))
            delete_category(key, move_to=target)

        self._mutate(work)

    @Slot(str, bool)
    def setEssential(self, key, essential):
        from services.queries import set_category_importance

        self._mutate(lambda: set_category_importance(key, essential), announce=False)
