"""Controllers for accounts, cards and the add-transaction form."""

from __future__ import annotations

import datetime

from PySide6.QtCore import Property, QObject, Signal, Slot

from app.controllers import display_title, format_amount, short_date
from services.background_task_manager import BackgroundTaskManager
from app.language import known_to_services, later, say, tr
from utils.formatters import parse_amount
from utils.logging_config import get_logger

CHECKING = "checking"
CREDIT_CARD = "credit_card"
GENERIC_FAILURE = later("This could not be saved. Check the values and try again.")
_NETWORKS = ("Visa", "Mastercard", "Troy")


class FormError(ValueError):
    """A problem with what the user typed; the text is already user-facing."""


def user_message(error: Exception) -> str:
    """The catalog's English text for a service refusal, or a safe fallback.

    Service messages are catalog keys. One that is missing from the catalog
    may carry raw input, so it is never shown as it is.
    """
    if isinstance(error, FormError):
        return str(error)
    text = str(error)
    return tr(text) if known_to_services(text) else say(GENERIC_FAILURE)


def is_explained(error: Exception) -> bool:
    """False when `user_message` can only give its general failure text."""
    return isinstance(error, FormError) or known_to_services(str(error))


def read_amount(text: str, label: str, *, optional: bool = False) -> float:
    text = (text or "").strip()
    if not text:
        if optional:
            return 0.0
        raise FormError(say("Enter the {0}.", label))
    try:
        return parse_amount(text)
    except ValueError:
        raise FormError(say("Enter a valid {0}, for example 1.250,50.", label)) from None


def read_date(text: str) -> str | None:
    """'DD.MM.YYYY' -> a full timestamp; empty means now."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        day = datetime.datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        raise FormError(say("Enter the date as DD.MM.YYYY, for example 08.10.2026.")) from None
    now = datetime.datetime.now()
    if day == now.date():
        return None
    return f"{day.isoformat()} {now:%H:%M:%S}"


class _Mutating(QObject):
    """Shared plumbing: run a write off the interface thread, report the outcome."""

    messageChanged = Signal()
    busyChanged = Signal()
    saved = Signal()
    dataChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(parent)
        self._tasks = tasks
        self._message = ""
        self._busy = False

    @Property(str, notify=messageChanged)
    def message(self):
        return self._message

    @Property(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @Slot()
    def clearMessage(self):
        self._set_message("")

    def _set_message(self, text: str) -> None:
        if text != self._message:
            self._message = text
            self.messageChanged.emit()

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def _mutate(self, work, *, announce: bool = True) -> None:
        if self._busy:
            return
        self._set_busy(True)

        def succeeded(_result):
            self._set_busy(False)
            self._set_message("")
            if announce:
                self.saved.emit()
            self.dataChanged.emit()

        def failed(error):
            self._set_busy(False)
            if not isinstance(error, ValueError):
                get_logger().exception(
                    "Kayıt işlemi başarısız.",
                    exc_info=(type(error), error, error.__traceback__),
                )
            self._set_message(user_message(error))

        self._tasks.submit(
            f"mutate-{id(self)}", lambda _cancel: work(),
            on_success=succeeded, on_error=failed, replace=False,
        )


class AccountsController(_Mutating):
    changed = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._accounts: list[dict] = []
        self._cash = "—"
        self._debt = "—"
        self.dataChanged.connect(self.refresh)

    # -- state ---------------------------------------------------------------
    @Property("QVariantList", notify=changed)
    def accounts(self):
        return self._accounts

    @Property("QVariantList", notify=changed)
    def options(self):
        """Every account, for pickers."""
        return [
            {
                "key": account["id"],
                "label": account["name"],
                "kind": account["kind"],
            }
            for account in self._accounts
        ]

    @Property("QVariantList", notify=changed)
    def checkingOptions(self):
        return [option for option in self.options if option["kind"] == CHECKING]

    @Property(str, notify=changed)
    def cashText(self):
        return self._cash

    @Property(str, notify=changed)
    def debtText(self):
        return self._debt

    @Slot()
    def refresh(self):
        self._tasks.submit(
            "accounts", lambda _cancel: self._load(),
            on_success=self._apply, on_error=self._load_failed, replace=True,
        )

    @staticmethod
    def _load() -> list[dict]:
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        accounts = AccountService.get_accounts()
        for account in accounts:
            account["recent"] = TransactionService.get_recent_for_account(
                account["id"], limit=3
            )
        return accounts

    def _apply(self, accounts: list[dict]) -> None:
        self._accounts = [self._view(account) for account in accounts]
        cash = sum(a["balance"] for a in accounts if a["account_type"] == CHECKING)
        debt = sum(a["debt"] for a in accounts if a["account_type"] == CREDIT_CARD)
        self._cash = f"{format_amount(cash)} ₺"
        self._debt = f"{format_amount(debt)} ₺"
        self.changed.emit()

    def _load_failed(self, error) -> None:
        get_logger().exception(
            "Hesaplar yüklenemedi.",
            exc_info=(type(error), error, error.__traceback__),
        )
        self._set_message(say("Accounts could not be loaded."))

    @staticmethod
    def _view(account: dict) -> dict:
        credit = account["account_type"] == CREDIT_CARD
        limit = account["credit_limit"]
        if credit:
            summary = say("{0} ₺ available", format_amount(account['available_limit']))
        else:
            summary = f"{format_amount(account['balance'])} ₺"
        network = next(
            (name for name in _NETWORKS if name.lower() in account["network_logo"].lower()),
            "",
        )
        return {
            "id": account["id"],
            "name": account["name"],
            "kind": account["account_type"],
            "typeLabel": tr(account["type_label"]),
            "summary": summary,
            "balanceText": ("−" if account["balance"] < 0 else "")
            + f"{format_amount(account['balance'])} ₺",
            "debtText": f"{format_amount(account['debt'])} ₺",
            "limitText": f"{format_amount(limit)} ₺",
            "availableText": f"{format_amount(account['available_limit'])} ₺",
            "hasDebt": account["debt"] > 0,
            "usage": min(1.0, account["debt"] / limit) if credit and limit > 0 else 0.0,
            "statementDay": account["statement_date"] or 0,
            "lastFour": account["masked_number"][-4:] if account["has_card_number"] else "",
            "network": network,
            "frozen": account["is_frozen"],
            "onlinePayments": account["online_payments_enabled"],
            "recent": [
                {
                    "date": short_date(item["date"]) if item["date"] else "",
                    "title": display_title(item["description"]),
                    "amount": ("+" if item["type"] == "income" else "−")
                    + format_amount(item["amount"]) + " ₺",
                    "income": item["type"] == "income",
                }
                for item in account["recent"]
            ],
        }

    # -- actions -------------------------------------------------------------
    @Slot(str, str, str, str, str, str)
    def addAccount(self, kind, name, balance_text, limit_text, statement_day, card_number):
        def work():
            from services.account_service import AccountService

            credit = kind == CREDIT_CARD
            balance = read_amount(
                balance_text, say("current debt") if credit else "balance", optional=True
            )
            limit = read_amount(limit_text, say("card limit")) if credit else 0.0
            digits = "".join(ch for ch in (card_number or "") if ch.isdigit())
            if digits and not 12 <= len(digits) <= 19:
                raise FormError(say("Enter the full card number, or leave it empty."))
            AccountService.create_account(
                name=name,
                account_type=kind,
                initial_balance=balance,
                credit_limit=limit,
                statement_date=(statement_day or "").strip() if credit else None,
                card_number_full=digits or None,
            )

        self._mutate(work)

    @Slot(int, bool)
    def setFrozen(self, account_id, frozen):
        from services.account_service import AccountService

        self._mutate(
            lambda: AccountService.set_card_frozen(account_id, frozen), announce=False
        )

    @Slot(int, bool)
    def setOnlinePayments(self, account_id, enabled):
        from services.account_service import AccountService

        self._mutate(
            lambda: AccountService.set_online_payments(account_id, enabled),
            announce=False,
        )

    @Slot(int, int, str)
    def payDebt(self, card_id, source_id, amount_text):
        def work():
            from services.account_service import AccountService

            if source_id < 0:
                raise FormError(say("Choose the account to pay from."))
            amount = read_amount(amount_text, say("amount"))
            card = AccountService.get_account(card_id)
            if card and 0 < card["debt"] < amount:
                raise FormError(
                    say("The payment cannot exceed the current debt of {0} ₺.", format_amount(card['debt']))
                )
            AccountService.pay_credit_card_debt(card_id, source_id, amount)

        self._mutate(work)

    @Slot(int)
    def deleteCard(self, card_id):
        from services.account_service import AccountService

        self._mutate(lambda: AccountService.delete_credit_card(card_id))


class TransactionFormController(_Mutating):
    stateChanged = Signal()
    categoriesChanged = Signal()

    def __init__(self, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._last_pending = False
        self._category_revision = 0
        self.saved.connect(self.stateChanged)

    @Property(str, notify=stateChanged)
    def todayText(self):
        return datetime.date.today().strftime("%d.%m.%Y")

    @Property(bool, notify=stateChanged)
    def lastWasPending(self):
        return self._last_pending

    @Property(int, notify=categoriesChanged)
    def categoryRevision(self):
        """Changes whenever the category list does; bindings read it to refresh."""
        return self._category_revision

    @Slot()
    def categoriesEdited(self):
        self._category_revision += 1
        self.categoriesChanged.emit()

    @Slot(str, result="QVariantList")
    def categories(self, transaction_type):
        from services.queries import CategoryService

        from services.transaction_edit_service import SYSTEM_CATEGORIES

        rows = CategoryService.get_categories(transaction_type)
        # Categories the application files its own records under are not
        # offered: a record put there by hand would look like one of them.
        options = [
            {"key": row[1], "label": tr(row[1])}
            for row in rows if row[1] not in SYSTEM_CATEGORIES
        ]
        return sorted(options, key=lambda option: option["label"].casefold())

    @Slot(int, result="QVariantMap")
    def details(self, transaction_id):
        """A transaction as the edit form shows it; empty when it is gone."""
        from services.transaction_edit_service import get_transaction

        try:
            found = get_transaction(transaction_id)
        except ValueError:
            return {}
        try:
            day = datetime.date.fromisoformat(found["date"][:10]).strftime("%d.%m.%Y")
        except ValueError:
            day = ""
        return {
            "id": found["id"],
            "kind": found["type"] if found["type"] in ("income", "expense") else "expense",
            "accountId": found["account_id"],
            "category": found["category"],
            "amountText": "" if found["amount"] is None else format_amount(found["amount"]),
            "description": found["description"],
            "dateText": day,
            "locked": tr(found["locked"]) if found["locked"] else "",
        }

    @Slot(int, str, str, str, str)
    def update(self, transaction_id, amount_text, category, description, date_text):
        def work():
            from services.transaction_edit_service import update_transaction

            if not category:
                raise FormError(say("Choose a category."))
            amount = read_amount(amount_text, say("amount"))
            stamp = read_date(date_text) or datetime.date.today().isoformat()
            update_transaction(
                transaction_id, amount, category, (description or "").strip(), stamp[:10],
            )
            self._last_pending = False

        self._mutate(work)

    @Slot(int)
    def remove(self, transaction_id):
        def work():
            from services.transaction_edit_service import delete_transaction

            delete_transaction(transaction_id)
            self._last_pending = False

        self._mutate(work)

    @Slot(str, str, int, str, str, str, int)
    def add(self, transaction_type, amount_text, account_id, category,
            description, date_text, installments):
        def work():
            from services.account_service import AccountService
            from services.transaction_service import TransactionService

            if account_id < 0:
                raise FormError(say("Choose an account."))
            if not category:
                raise FormError(say("Choose a category."))
            amount = read_amount(amount_text, say("amount"))
            stamp = read_date(date_text)
            account = AccountService.get_account(account_id)
            on_card = bool(
                account and account["account_type"] == CREDIT_CARD
                and transaction_type == "expense"
            )
            TransactionService.add_transaction(
                account_id, amount, transaction_type, category,
                (description or "").strip(),
                transaction_date=stamp,
                installments=installments if on_card and installments > 1 else None,
            )
            self._last_pending = bool(
                stamp and stamp[:10] > datetime.date.today().isoformat()
            )

        self._mutate(work)
