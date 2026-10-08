"""The interface loads and routes without a display.

Runs the real QML through Qt's offscreen platform. A QML warning counts as a
failure: a binding that silently stops working is how a blank screen ships.
"""

import os
import tempfile
import time
import unittest
from unittest import mock

try:
    from PySide6.QtCore import QCoreApplication, QtMsgType, qInstallMessageHandler
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

        self.app.fail("Geri yükleme tamamlanamadı", "Veritabanı doğrulanamadı")
        _pump(seconds=0.1)
        self.assertEqual(self.app.screen, "failure")

        self.assertEqual(self._warnings(), [])


if __name__ == "__main__":
    unittest.main()
