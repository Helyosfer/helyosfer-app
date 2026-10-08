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

from app.controllers import (
    AppController, AuthController, DashboardController, Dispatcher,
)
from utils.app_paths import data_dir, resource_dir

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
        auth = dashboard = None
    else:
        auth = AuthController(controller, AuthService(store), tasks, app)
        dashboard = DashboardController(tasks, app)
        auth.signedIn.connect(dashboard.refresh)
    context.setContextProperty("auth", auth)
    context.setContextProperty("dashboard", dashboard)

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
