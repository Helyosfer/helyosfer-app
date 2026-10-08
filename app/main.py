"""Application entry point: safe startup first, then the window."""

from __future__ import annotations

import atexit
import os
import sys
import threading

from PySide6.QtCore import QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from app.accounts import AccountsController, TransactionFormController
from app.assets import AssetsController
from app.payments import DebtsController, RecurringController
from app.insight import HistoryController, InsightsController, ScenarioController
from app.monthly import BudgetController, CalendarController
from app.calculators import CalculatorController, LoanController
from app.planning import SavingsController
from app.settings import SettingsController
from app.controllers import (
    AppController, AuthController, DashboardController, Dispatcher,
)
from utils.app_paths import data_dir, resource_dir
from utils.logging_config import get_logger

QML_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qml")


def _acquire_instance_lock():
    from utils.single_instance import (
        AlreadyRunningError, SingleInstanceLock, notify_already_running,
    )

    lock = SingleInstanceLock(os.path.join(data_dir(), "helysofer.instance.lock"))
    try:
        lock.acquire()
    except AlreadyRunningError as exc:
        notify_already_running(str(exc))
        raise SystemExit(2) from exc
    atexit.register(lock.release)
    return lock


def _warm_crypto_key() -> None:
    def warm():
        from utils.crypto import _get_aead_key
        from utils.errors import HelysoferError
        from utils.logging_config import get_logger

        try:
            _get_aead_key()
        except (HelysoferError, OSError):
            get_logger().exception("Şifreleme anahtarı arka planda ısıtılamadı")

    threading.Thread(target=warm, name="helysofer-key-warmup", daemon=True).start()


def prepare_profile(config_path: str):
    """Recovery, then the key, then the database -- in that order.

    Returns `None` when the profile is ready, or `(title, message)` built only
    from fixed user-facing text when startup must stop.
    """
    from database.db import migrate_legacy_database_location
    from database.init_db import (
        DATA_INTEGRITY_MESSAGE, SCHEMA_TOO_NEW_MESSAGE, initialize_database,
    )
    from services.startup_recovery import (
        DATA_INTEGRITY_TITLE, RECOVERY_FAILURE_TITLE, SCHEMA_TOO_NEW_TITLE,
        USER_MESSAGE, StartupRecoveryError, run_startup_recovery,
    )
    from utils.errors import FinancialDataIntegrityError, SchemaTooNewError
    from utils.logging_config import get_logger

    try:
        run_startup_recovery(config_path=config_path)
    except StartupRecoveryError as exc:
        get_logger().critical("Açılış kurtarması başarısız: %s", exc.outcome)
        return RECOVERY_FAILURE_TITLE, USER_MESSAGE

    _warm_crypto_key()
    migrate_legacy_database_location()
    try:
        initialize_database()
    except SchemaTooNewError as exc:
        get_logger().critical(
            "Veritabanı şeması bu yapıdan yeni: bulunan=%s desteklenen=%s",
            exc.found, exc.supported,
        )
        return SCHEMA_TOO_NEW_TITLE, SCHEMA_TOO_NEW_MESSAGE
    except FinancialDataIntegrityError as exc:
        get_logger().critical(
            "Veritabanı bütünlük kapısı açılışı durdurdu: "
            "table=%s id=%s field=%s reason=%s",
            exc.table, exc.record_id, exc.field, exc.reason,
        )
        return DATA_INTEGRITY_TITLE, DATA_INTEGRITY_MESSAGE
    return None


def build(app: QGuiApplication):
    """Wires services, controllers and the QML engine. Returns the engine."""
    from services.auth_service import AuthService
    from services.background_task_manager import BackgroundTaskManager
    from utils.config_store import ConfigStore, default_config_path
    from utils.ui_dispatch import set_main_thread_scheduler

    config_path = default_config_path()
    failure = prepare_profile(config_path)

    dispatcher = Dispatcher(app)
    set_main_thread_scheduler(dispatcher.post)
    tasks = BackgroundTaskManager(schedule=dispatcher.post)
    app.aboutToQuit.connect(lambda: tasks.shutdown(wait=False))

    store = None if failure else ConfigStore(config_path)
    controller = AppController(store, app)
    engine = QQmlApplicationEngine(app)
    context = engine.rootContext()
    context.setContextProperty("app", controller)

    if failure:
        auth = dashboard = accounts = transactions = debts = recurring = None
        settings = assets = savings = loan = budget = calendar = None
        insights = scenario = history = calc = None
    else:
        auth_service = AuthService(store)
        auth = AuthController(controller, auth_service, tasks, app)
        dashboard = DashboardController(tasks, app)
        accounts = AccountsController(tasks, app)
        transactions = TransactionFormController(tasks, app)
        debts = DebtsController(tasks, app)
        recurring = RecurringController(tasks, app)
        assets = AssetsController(tasks, app)
        savings = SavingsController(tasks, app)
        loan = LoanController(tasks, app)
        calc = CalculatorController(tasks, app)
        budget = BudgetController(tasks, app)
        calendar = CalendarController(tasks, app)
        insights = InsightsController(tasks, app)
        scenario = ScenarioController(tasks, app)
        history = HistoryController(tasks, app)

        # A write anywhere refreshes every view that shows money.
        views = (dashboard, accounts, debts, recurring, assets, savings, budget,
                 calendar, insights)
        for writer in (accounts, transactions, debts, recurring, assets, savings,
                       loan, insights, calc):
            for view in views:
                if view is not writer:
                    writer.dataChanged.connect(view.refresh)

        def refresh_all(_changed=None):
            for view in views:
                view.refresh()

        def settle_due_items():
            from services.scheduled_service import process_due_items

            tasks.submit(
                "due-items", lambda _cancel: process_due_items(),
                on_success=lambda changed: refresh_all() if changed else None,
                on_error=lambda error: get_logger().exception(
                    "Vadesi gelen kayıtlar işlenemedi.",
                    exc_info=(type(error), error, error.__traceback__),
                ),
            )

        auth.signedIn.connect(refresh_all)
        auth.signedIn.connect(settle_due_items)

        settings = SettingsController(auth_service, store, tasks, app)
        settings.dataChanged.connect(refresh_all)
        settings.passwordChanged.connect(auth.logout)
        settings.wiped.connect(auth.start)
        settings.wiped.connect(refresh_all)
        settings.restored.connect(lambda: controller.halt(
            "Backup restored",
            "Your records, encryption key and settings were replaced with the "
            "ones in the backup.",
            "Close Helysofer and open it again to continue.",
        ))
    context.setContextProperty("auth", auth)
    context.setContextProperty("dashboard", dashboard)
    context.setContextProperty("accounts", accounts)
    context.setContextProperty("transactions", transactions)
    context.setContextProperty("debts", debts)
    context.setContextProperty("recurring", recurring)
    context.setContextProperty("settings", settings)
    context.setContextProperty("assets", assets)
    context.setContextProperty("savings", savings)
    context.setContextProperty("loan", loan)
    context.setContextProperty("calc", calc)
    context.setContextProperty("budget", budget)
    context.setContextProperty("calendar", calendar)
    context.setContextProperty("insights", insights)
    context.setContextProperty("scenario", scenario)
    context.setContextProperty("history", history)

    engine.load(QUrl.fromLocalFile(os.path.join(QML_DIR, "Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError("The interface could not be loaded.")

    if failure:
        controller.fail(*failure)
    else:
        auth.start()
    return engine


def run() -> int:
    _acquire_instance_lock()
    os.chdir(resource_dir())
    QQuickStyle.setStyle("Basic")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("Helysofer")
    app.setWindowIcon(QIcon(os.path.join(resource_dir(), "assets", "icon.png")))
    engine = build(app)  # noqa: F841 -- keeps the engine alive for the event loop
    return app.exec()
