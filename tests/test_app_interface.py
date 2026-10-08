"""The interface loads and routes without a display.

Runs the real QML through Qt's offscreen platform. A QML warning counts as a
failure: a binding that silently stops working is how a blank screen ships.
"""

import datetime
import os
import tempfile
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
        cls._db.start()
        cls._config.start()

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
            or self.recurring.busy or self.dashboard.loading
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

        self.app.fail("Geri yükleme tamamlanamadı", "Veritabanı doğrulanamadı")
        _pump(seconds=0.1)
        self.assertEqual(self.app.screen, "failure")

        self.assertEqual(self._warnings(), [])


if __name__ == "__main__":
    unittest.main()
