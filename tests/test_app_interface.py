"""The interface loads and routes without a display.

Runs the real QML through Qt's offscreen platform. A QML warning counts as a
failure: a binding that silently stops working is how a blank screen ships.
"""

import datetime
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

try:
    from PySide6.QtCore import (
        QCoreApplication, QEvent, QtMsgType, qInstallMessageHandler,
    )
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuickControls2 import QQuickStyle
except ImportError:  # pragma: no cover - the interface toolkit is optional for core tests
    QGuiApplication = None

STRONG = "Guclu-Parola-2026!"
PRICES = {"THYAO": 312.5}


def _fixed_prices(assets, callback, item_callback=None, cache_callback=None,
                  force_refresh=False):
    """Stands in for the price service: fixed quotes, no network, no child process."""
    from services.asset_service import calculate_pnl

    enriched = []
    for asset in assets:
        entry = dict(asset)
        price = PRICES.get(asset["asset_code"])
        if price is None:
            entry.update({"current_price": None, "pnl_amount": None, "pnl_pct": None,
                          "total_value": None, "total_cost": None, "signal": "error"})
        else:
            entry.update(calculate_pnl(price, asset["purchase_price"], asset["quantity"]))
            entry["current_price"] = price
        enriched.append(entry)
    threading.Thread(target=lambda: callback(enriched), daemon=True).start()


def _pump(until=None, seconds=8.0):
    deadline = time.time() + seconds
    while time.time() < deadline:
        QCoreApplication.processEvents()
        if until is None or until():
            break
        time.sleep(0.01)
    for _ in range(10):
        QCoreApplication.processEvents()
    # `processEvents` skips deferred deletions, so a screen a Loader has
    # replaced would linger and be found by name instead of the live one.
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


@unittest.skipIf(QGuiApplication is None, "PySide6 is not installed")
class InterfaceSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["HELYSOFER_LANGUAGE"] = "en"
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        os.environ.setdefault("QT_QUICK_BACKEND", "software")
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        cls._db = mock.patch(
            "database.db.DB_NAME", os.path.join(cls._tmp.name, "finance.db")
        )
        cls._config = mock.patch(
            "utils.config_store.default_config_path",
            lambda: os.path.join(cls._tmp.name, "config.json"),
        )
        cls._prices = mock.patch(
            "services.asset_service.fetch_portfolio_with_prices", _fixed_prices
        )
        cls._db.start()
        cls._config.start()
        cls._prices.start()

        cls.messages = []
        qInstallMessageHandler(
            lambda kind, context, text: cls.messages.append((kind, text))
        )
        QQuickStyle.setStyle("Basic")
        cls.qt = QGuiApplication.instance() or QGuiApplication([])

        from app import main as app_main

        cls.engine = app_main.build(cls.qt)
        context = cls.engine.rootContext()
        cls.app = context.contextProperty("app")
        cls.auth = context.contextProperty("auth")
        cls.dashboard = context.contextProperty("dashboard")
        cls.accounts = context.contextProperty("accounts")
        cls.transactions = context.contextProperty("transactions")
        cls.debts = context.contextProperty("debts")
        cls.recurring = context.contextProperty("recurring")
        cls.settings = context.contextProperty("settings")
        cls.assets = context.contextProperty("assets")
        cls.savings = context.contextProperty("savings")
        cls.loan = context.contextProperty("loan")
        cls.calc = context.contextProperty("calc")
        cls.search = context.contextProperty("search")
        cls.categories = context.contextProperty("categories")
        cls.budget = context.contextProperty("budget")
        cls.calendar = context.contextProperty("calendar")
        cls.insights = context.contextProperty("insights")
        cls.scenario = context.contextProperty("scenario")
        cls.history = context.contextProperty("history")
        _pump(seconds=0.2)

    @classmethod
    def tearDownClass(cls):
        from utils.ui_dispatch import set_main_thread_scheduler

        _pump(lambda: not cls.dashboard.loading and not cls.auth.busy)
        for window in cls.engine.rootObjects():
            window.close()
        cls.engine.deleteLater()
        _pump(seconds=0.2)
        set_main_thread_scheduler(None)
        qInstallMessageHandler(None)
        cls._prices.stop()
        cls._config.stop()
        cls._db.stop()
        cls._tmp.cleanup()

    def _warnings(self):
        return [
            text for kind, text in self.messages
            if kind != QtMsgType.QtDebugMsg and "font" not in text.lower()
        ]

    def _settle(self):
        _pump(lambda: not (
            self.accounts.busy or self.transactions.busy or self.debts.busy
            or self.recurring.busy or self.settings.busy or self.auth.busy
            or self.assets.busy or self.savings.busy or self.loan.busy
            or self.budget.busy or self.insights.busy or self.scenario.busy
            or self.calc.busy or self.categories.busy or self.search.searching
            or self.history.busy
            or self.dashboard.loading
        ))
        # Let the reloads a write triggers come back before reading state.
        deadline = time.time() + 0.15
        while time.time() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)

    def _accounts_and_transactions(self):
        from PySide6.QtCore import QMetaObject, QObject, Q_ARG

        window = self.engine.rootObjects()[0]
        shell = window.findChild(QObject, "shell")
        shell.setProperty("section", "cards")
        self._settle()

        self.accounts.addAccount("credit_card", "Travel card", "3.200", "", "15", "")
        self._settle()
        self.assertEqual(self.accounts.message, "Enter the card limit.")
        self.accounts.addAccount(
            "credit_card", "Travel card", "3.200", "25.000", "15", "4543123456789012"
        )
        self._settle()
        self.assertEqual(self.accounts.message, "")
        main, card = self.accounts.accounts
        self.assertEqual(card["lastFour"], "9012")
        self.assertEqual(card["network"], "Visa")
        self.assertEqual(card["debtText"], "3.200,00 ₺")

        self.transactions.add("expense", "", main["id"], "Süpermarket", "", "", 1)
        self._settle()
        self.assertEqual(self.transactions.message, "Enter the amount.")
        self.transactions.add(
            "expense", "500,50", main["id"], "Süpermarket", "Weekly shop", "", 1
        )
        self._settle()
        self.assertEqual(self.transactions.message, "")
        self.transactions.add(
            "expense", "6.000", card["id"], "Tatil/Konaklama", "Hotel", "", 6
        )
        self._settle()
        self.accounts.payDebt(card["id"], main["id"], "99.999")
        self._settle()
        self.assertIn("cannot exceed", self.accounts.message)
        self.accounts.payDebt(card["id"], main["id"], "200")
        self._settle()

        main, card = self.accounts.accounts
        self.assertEqual(main["balanceText"], "800,00 ₺")
        self.assertEqual(card["debtText"], "9.000,00 ₺")
        self.assertEqual(self.accounts.cashText, "800,00 ₺")
        self.assertEqual(card["recent"][0]["title"], "Travel card debt payment")
        self.assertEqual(self.dashboard.recent[0]["title"], "Travel card debt payment")

        self.accounts.setFrozen(card["id"], True)
        self._settle()
        self.transactions.add("expense", "10", card["id"], "Taksi", "", "", 1)
        self._settle()
        self.assertIn("frozen", self.transactions.message)
        self.transactions.clearMessage()

        def shows(name, method, *arguments):
            dialog = window.findChild(QObject, name)
            QMetaObject.invokeMethod(
                dialog, method, *[Q_ARG("QVariant", value) for value in arguments]
            )
            self.assertTrue(dialog.property("visible"), (name, self._warnings()))
            dialog.setProperty("visible", False)

        # A list that is rebuilt under an open form keeps what was chosen
        # there, and never picks its first entry on the user's behalf.
        form = window.findChild(QObject, "addTransaction")
        QMetaObject.invokeMethod(form, "openFor", Q_ARG("QVariant", card["id"]))
        self.assertEqual(form.property("chosenAccount"), card["id"])
        self.assertIsNone(form.property("chosenCategory"))
        form.setProperty("kind", "income")
        self._settle()
        self.assertIsNone(form.property("chosenCategory"))
        self.accounts.refresh()
        self.transactions.categoriesEdited()
        self._settle()
        self.assertEqual(form.property("chosenAccount"), card["id"])
        self.assertIsNone(form.property("chosenCategory"))
        form.setProperty("visible", False)

        # Changing and removing a transaction through the same form.
        self.accounts.setFrozen(card["id"], False)
        self._settle()
        before = self.accounts.accounts[0]["balanceText"]
        self.transactions.add("expense", "40", main["id"], "Taksi", "Night ride", "", 1)
        self._settle()
        ride = self.dashboard.recent[0]
        self.assertEqual((ride["title"], ride["amount"]), ("Night ride", "−40,00 ₺"))
        QMetaObject.invokeMethod(form, "openForEdit", Q_ARG("QVariant", ride["id"]))
        self.assertTrue(form.property("visible"), self._warnings())
        self.assertEqual(form.property("editing"), ride["id"])
        self.assertEqual(form.property("locked"), "")
        self.assertEqual(form.property("chosenAccount"), main["id"])
        self.assertEqual(form.property("chosenCategory"), "Taksi")
        self.transactions.update(ride["id"], "", "Taksi", "Night ride", "")
        self._settle()
        self.assertEqual(self.transactions.message, "Enter the amount.")
        self.assertTrue(form.property("visible"))
        self.transactions.update(ride["id"], "65,50", "Süpermarket", "Late shop", "")
        self._settle()
        self.assertEqual(self.transactions.message, "")
        self.assertFalse(form.property("visible"))
        changed = self.dashboard.recent[0]
        self.assertEqual(
            (changed["id"], changed["title"], changed["category"], changed["amount"]),
            (ride["id"], "Late shop", "Groceries", "−65,50 ₺"),
        )
        self.transactions.remove(ride["id"])
        self._settle()
        self.assertNotIn(ride["id"], [row["id"] for row in self.dashboard.recent])
        self.assertEqual(self.accounts.accounts[0]["balanceText"], before)
        self.assertEqual(self.transactions.details(ride["id"]), {})

        # A record the application wrote opens locked.
        payment = next(row for row in self.dashboard.recent
                       if row["title"] == "Travel card debt payment")
        QMetaObject.invokeMethod(form, "openForEdit", Q_ARG("QVariant", payment["id"]))
        self.assertTrue(form.property("visible"), self._warnings())
        self.assertIn("cannot be changed here", form.property("locked"))
        self.transactions.remove(payment["id"])
        self._settle()
        self.assertIn("cannot be changed here", self.transactions.message)
        self.transactions.clearMessage()
        form.setProperty("visible", False)
        self.assertNotIn(
            "Debt Payment", [c["label"] for c in self.transactions.categories("expense")]
        )
        self.accounts.setFrozen(card["id"], True)
        self._settle()

        shows("addTransaction", "openFor", card["id"])
        shows("payDebt", "openFor", card)
        shows("confirmDelete", "openFor", card)
        shows("addAccount", "openFresh")

        self.accounts.deleteCard(card["id"])
        self._settle()
        self.assertEqual(len(self.accounts.accounts), 1)

        # -- debts and pending transactions --------------------------------
        shell.setProperty("section", "debts")
        self._settle()
        self.debts.addDebt("", "100", "3", False, "")
        self._settle()
        self.assertEqual(self.debts.message, "Enter a name for the debt.")
        self.debts.addDebt("Phone", "100", "3", False, "")
        self._settle()
        debt = self.debts.debts[0]
        self.assertEqual(debt["remainingText"], "300,00 ₺")
        self.debts.pay(debt["id"], main["id"], 5)
        self._settle()
        self.assertIn("more installments", self.debts.message)
        self.debts.pay(debt["id"], main["id"], 1)
        self._settle()
        self.assertEqual(self.debts.debts[0]["progressText"], "1 of 3 paid")
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "700,00 ₺")

        later = (datetime.date.today() + datetime.timedelta(days=8)).strftime("%d.%m.%Y")
        self.transactions.add("expense", "50", main["id"], "İnternet", "Fiber", later, 1)
        self._settle()
        self.assertEqual(len(self.debts.pending), 1)
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "700,00 ₺")
        shows("addDebt", "openFresh")
        shows("payInstallments", "openFor", self.debts.debts[0], False)
        shows("autoPayDay", "openFor", self.debts.debts[0], "1")
        shows("reschedule", "openFor", self.debts.pending[0], "")
        self.debts.cancelPending(self.debts.pending[0]["id"])
        self._settle()
        self.assertEqual(self.debts.pending, [])
        self.debts.pay(debt["id"], main["id"], 0)
        self._settle()
        self.assertEqual(self.debts.debts, [])
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "500,00 ₺")

        # -- assets ---------------------------------------------------------
        shell.setProperty("section", "assets")
        self._settle()
        self.assets.buy("Hisse", "", "", "10", "250", main["id"], True)
        self._settle()
        self.assertEqual(self.assets.message, "Enter the symbol.")
        self.assets.buy("Hisse", "thyao", "Turkish Airlines", "2", "100", main["id"], True)
        self._settle()
        _pump(lambda: not self.assets.pricing and len(self.assets.holdings) == 1)
        self._settle()
        holding = self.assets.holdings[0]
        self.assertEqual(holding["code"], "THYAO")
        self.assertEqual(holding["valueText"], "625,00 ₺")
        self.assertEqual(self.assets.pnlDirection, 1)
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "300,00 ₺")
        self.assets.lookUp("Hisse", "THYAO")
        _pump(lambda: not self.assets.quoteBusy)
        self.assertEqual(self.assets.quote, "312,50")
        shows("addAsset", "openFresh")
        shows("sellAsset", "openFor", holding)
        self.assets.sell(holding["id"], "5", "312,50", main["id"])
        self._settle()
        self.assertEqual(self.assets.message, "You cannot sell more than you hold.")
        self.assets.sell(holding["id"], "", "100", main["id"])
        self._settle()
        self.assertEqual(self.assets.holdings, [])
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "500,00 ₺")
        self.assertEqual(self.assets.history[0]["title"], "Sold 2 × Turkish Airlines (THYAO)")

        # -- savings goals --------------------------------------------------
        shell.setProperty("section", "savings")
        self._settle()
        self.savings.addGoal("", "1.000", "")
        self._settle()
        self.assertEqual(self.savings.message, "Enter a name for the goal.")
        self.savings.addGoal("Holiday", "1.000", "")
        self._settle()
        goal = self.savings.goals[0]
        self.savings.move(goal["id"], goal["uid"], "200", main["id"], True)
        self._settle()
        self.assertEqual(self.savings.goals[0]["savedText"], "200,00 ₺")
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "300,00 ₺")
        self.savings.move(goal["id"], goal["uid"], "500", main["id"], False)
        self._settle()
        self.assertEqual(self.savings.message, "The goal does not hold that much.")
        self.savings.move(goal["id"], "not-this-goal", "10", main["id"], True)
        self._settle()
        self.assertTrue(self.savings.message)
        self.assertEqual(self.savings.goals[0]["savedText"], "200,00 ₺")
        shows("addGoal", "openFresh")
        shows("moveSavings", "openFor", self.savings.goals[0], "deposit")
        shows("moveSavings", "openFor", self.savings.goals[0], "delete")
        self.savings.deleteGoal(goal["id"], goal["uid"], -1)
        self._settle()
        self.assertIn("receives the saved money", self.savings.message)
        self.savings.deleteGoal(goal["id"], goal["uid"], main["id"])
        self._settle()
        self.assertEqual(self.savings.goals, [])
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "500,00 ₺")

        # -- loan calculator ------------------------------------------------
        shell.setProperty("section", "tools")
        self._settle()
        self.loan.calculate("100.000", "x", "12", True, False, "")
        self.assertFalse(self.loan.hasResult)
        self.assertTrue(self.loan.message)
        self.loan.calculate("100.000", "3,49", "12", True, False, "")
        self.assertTrue(self.loan.hasResult)
        self.assertEqual(self.loan.monthlyText, "10.989,84 ₺")
        self.assertEqual(len(self.loan.schedule), 12)
        self.assertFalse(self.loan.hasDeductions)
        self.loan.addCharge("Insurance", "2.400", True, "12")
        self.loan.calculate("100.000", "3,49", "48", True, True, "consumer")
        self.assertIn("longer than this kind of loan allows", self.loan.message)
        self.loan.calculate("100.000", "3,49", "24", True, True, "consumer")
        self.assertTrue(self.loan.hasDeductions)
        self.assertTrue(self.loan.hasExtras)
        self.assertEqual(self.loan.schedule[0]["extra"], "200,00")
        plan = os.path.join(self._tmp.name, "plan")
        self.loan.exportPdf(plan)
        self._settle()
        self.assertTrue(os.path.exists(plan + ".pdf"))
        self.loan.removeCharge(0)
        self.loan.calculate("100.000", "3,49", "12", True, False, "")
        self.loan.addToDebts("Car loan")
        self._settle()
        self.assertEqual(self.loan.note, "Added to your debts.")

        window.findChild(QObject, "tools").setProperty("tool", "loan")
        self._settle()
        calculators = window.findChild(QObject, "calculators")
        for key in ("interest", "growth", "goal", "plain", "loan"):
            calculators.setProperty("calculator", key)
            self._settle()
        self.calc.interest("100.000", "45", "32")
        self.assertEqual(self.calc.interestRows[0]["value"], "+3.747,95 ₺")
        self.calc.growth("1.000", "10", "2", "")
        self.assertEqual(self.calc.growthSeries, [1000.0, 1100.0, 1210.0])
        self.calc.goalTime("1.000", "250", False)
        self.assertEqual(self.calc.goalRows[0]["value"], "4 months")
        self.calc.evaluate("(2 + 3) * 4")
        self.assertEqual(self.calc.answer, "20")
        self.calc.evaluate("__import__('os')")
        self.assertEqual(self.calc.answer, "")
        self.assertTrue(self.calc.message)
        self.calc.clearMessage()
        self.assertEqual(self.debts.debts[0]["monthlyText"], "10.989,84 ₺")

        # -- budget plan and calendar ---------------------------------------
        tools = window.findChild(QObject, "tools")
        tools.setProperty("tool", "budget")
        self._settle()
        self.budget.addItem("expense", "", "100", "", False)
        self._settle()
        self.assertEqual(self.budget.message, "Enter a name for the plan item.")
        self.budget.addItem("income", "Salary", "5.000", "Maaş", True)
        self._settle()
        self.budget.addItem("expense", "Groceries", "400", "Süpermarket", False)
        self._settle()
        self.assertEqual(self.budget.incomeText, "5.000,00 ₺")
        self.assertEqual(self.budget.expenseText, "400,00 ₺")
        self.assertEqual(self.budget.leftText, "4.600,00 ₺")
        groceries = self.budget.progress[0]
        self.assertEqual(groceries["category"], "Groceries")
        self.assertEqual(groceries["spentText"], "500,50 ₺")
        self.assertTrue(groceries["over"])
        shows("addPlanItem", "openFresh")

        item = next(i for i in self.budget.items if i["name"] == "Groceries")
        shows("addPlanItem", "openFor", item)
        self.budget.saveItem(
            item["id"], "expense", "Groceries", "600", "Süpermarket", False, True, "500"
        )
        self._settle()
        self.assertIn("warning level", self.budget.message)
        self.budget.saveItem(
            item["id"], "expense", "Groceries", "600", "Süpermarket", False, True, "50"
        )
        self._settle()
        self.assertEqual(self.budget.message, "")
        groceries = self.budget.progress[0]
        self.assertEqual(groceries["plannedText"], "600,00 ₺")
        self.assertFalse(groceries["over"])
        self.assertTrue(groceries["near"])
        edited = next(i for i in self.budget.items if i["name"] == "Groceries")
        self.assertTrue(edited["rollover"])
        self.assertEqual(edited["threshold"], 50)
        self.assertEqual(len(self.budget.items), 2)

        salary = next(i for i in self.budget.items if i["name"] == "Salary")
        self.assertTrue(salary["everyMonth"])
        self.budget.saveItem(salary["id"], "income", "Salary", "5.500", "Maaş", False, False, "80")
        self._settle()
        salary = next(i for i in self.budget.items if i["name"] == "Salary")
        self.assertEqual(salary["amountText"], "5.500,00 ₺")
        self.assertFalse(salary["everyMonth"])
        self.assertEqual(self.budget.incomeText, "5.500,00 ₺")

        self.budget.next()
        self._settle()
        self.assertEqual(self.budget.incomeText, "5.000,00 ₺")
        carried = next(
            (row for row in self.budget.progress if row["category"] == "Groceries"), None
        )
        self.assertIsNone(carried)
        self.budget.previous()
        self._settle()
        self.budget.next()
        self._settle()
        self.assertEqual([item["name"] for item in self.budget.items], ["Salary"])
        self.budget.previous()
        self._settle()
        # Removing this month's own Salary uncovers the repeating one again,
        # so keep removing until nothing is left.
        for _ in range(6):
            if not self.budget.items:
                break
            self.budget.deleteItem(self.budget.items[0]["id"])
            self._settle()
        self.assertEqual(self.budget.items, [])

        tools.setProperty("tool", "calendar")
        self._settle()
        today = datetime.date.today()
        self.assertEqual(self.calendar.selectedDay, today.day)
        self.assertEqual(len(self.calendar.cells) % 7, 0)
        marked = next(cell for cell in self.calendar.cells if cell["today"])
        self.assertGreater(marked["count"], 0)
        self.assertGreater(len(self.calendar.dayItems), 0)
        self.calendar.previous()
        self._settle()
        self.calendar.next()
        self._settle()
        tools.setProperty("tool", "insights")
        self._settle()
        # A day of history is enough for a score but not for a forecast.
        self.assertTrue(self.insights.healthNote)
        if self.insights.healthReady:
            self.assertTrue(self.insights.score.isdigit())
            self.assertEqual(len(self.insights.healthRows), 3)
        self.assertFalse(self.insights.forecastReady)
        self.assertIn("three months", self.insights.forecastNote)
        self.assertEqual(self.insights.message, "")

        tools.setProperty("tool", "scenario")
        self._settle()
        self.assertTrue(self.scenario.hasResult)
        self.scenario.run("x", "", "", "90")
        self.assertIn("percentage", self.scenario.message)
        self.scenario.run("0", "0", "1.000", "30")
        self._settle()
        self.assertEqual(self.scenario.message, "")
        self.assertEqual(self.scenario.differenceDirection, 1)
        self.assertEqual(len(self.scenario.scenarioSeries), len(self.scenario.baseSeries))
        self.assertEqual(len(self.scenario.labels), len(self.scenario.baseSeries))

        tools.setProperty("tool", "history")
        self._settle()
        self.history.lookUp("not a date")
        self.assertIn("DD.MM.YYYY", self.history.message)
        self.history.lookUp(today.strftime("%d.%m.%Y"))
        self._settle()
        self.assertTrue(self.history.hasResult)
        self.assertEqual(self.history.balanceText, self.accounts.accounts[0]["balanceText"])
        self.history.lookUp((today - datetime.timedelta(days=4000)).strftime("%d.%m.%Y"))
        self._settle()
        self.assertFalse(self.history.hasResult)
        self.assertIn("no records that far back", self.history.message)

        tools.setProperty("tool", "loan")
        self._settle()

        # -- overview: search and coming up -----------------------------------
        shell.setProperty("section", "overview")
        self._settle()
        self.search.search("weekly")
        self._settle()
        self.assertTrue(self.search.active)
        hit = next(r for r in self.search.results if r["kind"] == "Transaction")
        self.assertEqual(hit["title"], "Weekly shop")
        self.assertEqual(hit["target"], "calendar")
        self.search.search("main acc")
        self._settle()
        self.assertEqual(
            [(r["kind"], r["title"], r["target"]) for r in self.search.results],
            [("Account", "Main account", "cards")],
        )
        # A built-in category is found by the name shown on screen as well.
        self.search.search("groceries")
        self._settle()
        self.assertEqual(
            [(r["kind"], r["title"]) for r in self.search.results if r["kind"] == "Category"],
            [("Category", "Groceries")],
        )
        self.search.search("nothing-matches-this")
        self._settle()
        self.assertEqual(self.search.results, [])
        QMetaObject.invokeMethod(
            shell, "open", Q_ARG("QVariant", "calendar"), Q_ARG("QVariant", hit["argument"])
        )
        self._settle()
        self.assertFalse(self.search.active)
        self.assertEqual(shell.property("section"), "tools")
        self.assertEqual(window.findChild(QObject, "tools").property("tool"), "calendar")
        self.assertGreater(len(self.calendar.dayItems), 0)
        shell.setProperty("section", "overview")
        self._settle()

        soon = (datetime.date.today() + datetime.timedelta(days=4)).strftime("%d.%m.%Y")
        self.transactions.add("expense", "75", main["id"], "İnternet", "Fiber", soon, 1)
        self._settle()
        coming = self.dashboard.upcoming
        self.assertEqual(len(coming), 1)
        self.assertEqual(
            (coming[0]["title"], coming[0]["when"], coming[0]["section"], coming[0]["amount"]),
            ("Fiber", "in 4 days", "debts", "−75,00 ₺"),
        )
        self.debts.cancelPending(self.debts.pending[0]["id"])
        self._settle()
        self.dashboard.refresh()
        self._settle()
        self.assertEqual(self.dashboard.upcoming, [])

        # -- categories -----------------------------------------------------
        shell.setProperty("section", "settings")
        self._settle()
        self.assertGreater(len(self.categories.items), 50)
        self.categories.add("expense", "", False)
        self._settle()
        self.assertEqual(self.categories.message, "Enter a name for the category.")
        revision = self.transactions.categoryRevision
        self.categories.add("expense", "Pet sitter", True)
        self._settle()
        self.assertEqual(self.categories.message, "")
        added = next(c for c in self.categories.items if c["key"] == "Pet sitter")
        self.assertTrue(added["essential"])
        self.assertGreater(self.transactions.categoryRevision, revision)
        self.assertIn("Pet sitter", [c["key"] for c in self.transactions.categories("expense")])
        self.categories.add("expense", "PET SITTER", False)
        self._settle()
        self.assertIn("already exists", self.categories.message)
        self.categories.clearMessage()
        self.assertTrue(added["custom"])
        self.assertFalse(next(c for c in self.categories.items if c["key"] == "Taksi")["custom"])
        self.categories.rename("Pet sitter", "Dog walker")
        self._settle()
        self.assertEqual(self.categories.message, "")
        self.assertIn("Dog walker", [c["key"] for c in self.transactions.categories("expense")])
        self.categories.rename("Taksi", "Cab")
        self._settle()
        self.assertIn("Built-in", self.categories.message)
        self.categories.clearMessage()
        self.categories.remove("Dog walker")
        self._settle()
        self.assertNotIn("Dog walker", [c["key"] for c in self.categories.items])
        self.categories.add("expense", "Pet sitter", True)
        self._settle()
        self.categories.setEssential("Pet sitter", False)
        self._settle()
        added = next(c for c in self.categories.items if c["key"] == "Pet sitter")
        self.assertFalse(added["essential"])
        shell.setProperty("section", "tools")
        self._settle()

        # -- recurring payments --------------------------------------------
        shell.setProperty("section", "subscriptions")
        self._settle()
        today = datetime.date.today().strftime("%d.%m.%Y")
        self.recurring.add(
            "expense", "Music", "60", "Dijital Platformlar", "monthly", today,
            False, main["id"],
        )
        self._settle()
        self.assertEqual(self.recurring.message, "")
        item = self.recurring.items[0]
        self.assertEqual(item["amountText"], "60,00 ₺")
        self.recurring.payNow(item["id"])
        self._settle()
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "440,00 ₺")
        self.assertEqual(self.recurring.chargeThisMonth(item["id"]), "60,00 ₺")
        self.recurring.changeAmount(item["id"], "75")
        self._settle()
        self.assertEqual(self.recurring.items[0]["amountText"], "75,00 ₺")
        shows("addRecurring", "openFresh")
        shows("changeAmount", "openFor", self.recurring.items[0], "")
        shows("stopRecurring", "openFor", self.recurring.items[0])
        self.recurring.cancel(item["id"], True)
        self._settle()
        self.assertEqual(self.recurring.items, [])
        self.assertEqual(self.accounts.accounts[0]["balanceText"], "500,00 ₺")
        shell.setProperty("section", "overview")
        self._settle()

    def _language(self):
        """Switching the language rebuilds the screens and the controllers' text."""
        import json

        from PySide6.QtCore import QObject

        from app import language

        window = self.engine.rootObjects()[0]
        self.assertEqual(self.app.language, "en")
        self.assertEqual(
            [entry["label"] for entry in self.app.languages], ["English", "Türkçe"])
        english_shell = window.findChild(QObject, "shell")
        self.transactions.add("expense", "", self.accounts.accounts[0]["id"], "Taksi", "", "", 1)
        self._settle()
        self.assertEqual(self.transactions.message, "Enter the amount.")

        self.app.setLanguage("tr")
        self._settle()
        try:
            self.assertEqual((self.app.language, language.language()), ("tr", "tr"))
            shell = window.findChild(QObject, "shell")
            self.assertIsNot(shell, english_shell)
            # It comes back where it was, not on the overview.
            self.assertEqual(shell.property("section"), "settings")
            self.assertEqual(self._warnings(), [])
            self.assertEqual(self.accounts.accounts[0]["typeLabel"], "Nakit / Vadesiz")
            self.assertEqual(
                [period["label"] for period in self.dashboard.periods], ["Bugün", "1H", "1A", "1Y"])
            self.transactions.add("expense", "", self.accounts.accounts[0]["id"], "Taksi", "", "", 1)
            self._settle()
            self.assertEqual(self.transactions.message, "Lütfen tutar girin.")
            self.assertIn(
                "Taksi", [option["label"] for option in self.transactions.categories("expense")])
            with open(os.path.join(self._tmp.name, "config.json"), encoding="utf-8") as stream:
                self.assertEqual(json.load(stream)["display"]["language"], "tr")
            self.app.setLanguage("xx")
            self.assertEqual(self.app.language, "tr")
        finally:
            self.app.setLanguage("en")
            self._settle()
        self.transactions.clearMessage()
        self.assertEqual(language.language(), "en")
        self.assertEqual(self.accounts.accounts[0]["typeLabel"], "Cash / Checking")
        self.assertIn(
            "Taxi", [option["label"] for option in self.transactions.categories("expense")])
        # The theme setting saved earlier is still there next to the language.
        self.app.toggleTheme()
        with open(os.path.join(self._tmp.name, "config.json"), encoding="utf-8") as stream:
            display = json.load(stream)["display"]
        self.assertEqual((display["language"], display["style"]), ("en", "Light"))
        self.app.toggleTheme()

    def _settings(self):
        from PySide6.QtCore import QObject

        window = self.engine.rootObjects()[0]
        window.findChild(QObject, "shell").setProperty("section", "settings")
        self._settle()
        folder = self._tmp.name
        self._language()

        backup = os.path.join(folder, "copy")
        self.settings.createBackup(backup, "short", "short")
        self._settle()
        self.assertIn("at least 12", self.settings.message)
        self.settings.createBackup(backup, "yedek-parolasi-uzun", "yedek-parolasi-uzun")
        self._settle()
        self.assertEqual(self.settings.message, "")
        self.assertTrue(os.path.exists(backup + ".helysofer-backup"))

        self.settings.restoreBackup(backup + ".helysofer-backup", "yanlis-parola-uzun")
        self._settle()
        self.assertIn("could not be restored", self.settings.message)
        self.assertEqual(self.app.screen, "home")

        export = os.path.join(folder, "rows")
        self.settings.exportCsv(export)
        self._settle()
        self.assertTrue(os.path.exists(export + ".csv"))
        self.assertIn("Exported", self.settings.notice)

        # A file that cannot be read or written says so, not "check the values".
        account = self.accounts.accounts[0]["id"]
        with open(os.path.join(folder, "picture.csv"), "wb") as stream:
            stream.write(bytes(range(256)) * 8)
        for unreadable in ("picture.csv", "missing.csv"):
            self.settings.importCsv(os.path.join(folder, unreadable), account)
            self._settle()
            self.assertIn("could not be read", self.settings.message, unreadable)
        self.settings.exportCsv(os.path.join(folder, "picture.csv", "rows"))
        self._settle()
        self.assertIn("could not be saved there", self.settings.message)
        self.settings.clearMessage()

        self.settings.changePassword("wrong", "Baska-Parola-2027?", "Baska-Parola-2027?")
        self._settle()
        self.assertEqual(self.settings.message, "Incorrect password!")
        self.settings.changePassword(STRONG, "Baska-Parola-2027?", "Baska-Parola-2027?")
        self._settle()
        self.assertEqual(self.app.screen, "login")
        self.auth.login("Baska-Parola-2027?")
        _pump(lambda: self.app.screen == "home")
        self._settle()

        self.settings.resetAll("no")
        self._settle()
        self.assertIn("DELETE", self.settings.message)
        self.settings.resetAll("delete")
        self._settle()
        self.assertEqual(self.app.screen, "setup")
        self.assertEqual(self.accounts.accounts, [])

    def test_the_whole_first_run_path_works_without_qml_warnings(self):
        self.assertEqual(self.app.screen, "setup")

        self.auth.setup("1234", "1234")
        _pump(lambda: not self.auth.busy and self.auth.message != "")
        self.assertEqual(self.app.screen, "setup")
        self.assertTrue(self.auth.message)

        self.auth.setup(STRONG, STRONG)
        _pump(lambda: self.app.screen == "account_setup")
        self.assertEqual(self.app.screen, "account_setup")

        self.auth.createFirstAccount("Main account", "1.500,50")
        _pump(lambda: self.app.screen == "home")
        self.assertEqual(self.app.screen, "home")

        _pump(lambda: not self.dashboard.loading and self.dashboard.balanceWhole != "—")
        self.assertEqual(self.dashboard.balanceWhole, "1.500")
        self.assertEqual(self.dashboard.balanceFraction, ",50 ₺")
        self.assertEqual(self.dashboard.error, "")

        self.dashboard.setPeriod("1 Yıl")
        _pump(lambda: not self.dashboard.loading)
        self.app.toggleTheme()
        _pump(seconds=0.1)
        self.app.toggleTheme()

        self.auth.logout()
        _pump(lambda: self.app.screen == "login")
        self.auth.login("wrong-password")
        _pump(lambda: not self.auth.busy and self.auth.message != "")
        self.assertEqual(self.app.screen, "login")
        self.auth.login(STRONG)
        _pump(lambda: self.app.screen == "home")
        self.assertEqual(self.app.screen, "home")

        self._accounts_and_transactions()
        self._settings()

        self.app.fail("Geri yükleme tamamlanamadı", "Veritabanı doğrulanamadı")
        _pump(seconds=0.1)
        self.assertEqual(self.app.screen, "failure")

        self.assertEqual(self._warnings(), [])


if __name__ == "__main__":
    unittest.main()
