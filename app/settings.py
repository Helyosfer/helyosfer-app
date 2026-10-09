"""Controller for the settings screen: password, backups, CSV and reset."""

from __future__ import annotations

import os

from PySide6.QtCore import Property, QUrl, Signal, Slot

import database.db

from app.accounts import FormError, _Mutating
from app.controllers import format_amount
from app.language import later, say
from services.background_task_manager import BackgroundTaskManager
from utils.logging_config import get_logger

BACKUP_SUFFIX = ".helyosfer-backup"
CONTACT_EMAIL = "cakirgozmehmetc@proton.me"
PROJECT_URL = "github.com/Helyosfer/helyosfer-app"
UNWRITABLE = later("The file could not be saved there. Choose another location.")
UNREADABLE_CSV = later("This file could not be read. Choose a CSV file exported from Helyosfer.")


def local_path(url: str, suffix: str = "") -> str:
    """A file dialog's URL as a local path, with `suffix` ensured."""
    path = QUrl(url).toLocalFile() if "://" in (url or "") else (url or "")
    if not path:
        raise FormError(say("Choose a file first."))
    if suffix and not path.lower().endswith(suffix):
        path += suffix
    return path


class SettingsController(_Mutating):
    noticeChanged = Signal()
    passwordChanged = Signal()
    restored = Signal()
    wiped = Signal()

    def __init__(self, auth, store, tasks: BackgroundTaskManager, parent=None):
        super().__init__(tasks, parent)
        self._auth = auth
        self._store = store
        self._notice = ""

    # -- state ---------------------------------------------------------------
    @Property(str, notify=noticeChanged)
    def notice(self):
        """The outcome of the last successful action."""
        return self._notice

    def _set_notice(self, text: str) -> None:
        if text != self._notice:
            self._notice = text
            self.noticeChanged.emit()

    @Property(str, constant=True)
    def keyProtection(self):
        from utils.crypto import key_protection_status

        status = key_protection_status()
        return status.method

    @Property(str, constant=True)
    def keyWarning(self):
        from utils.crypto import key_protection_status

        status = key_protection_status()
        return "" if status.secure_store else (status.warning or "")

    @Property(str, constant=True)
    def dataFolder(self):
        from utils.app_paths import data_dir

        return data_dir()

    @Property(str, constant=True)
    def contactEmail(self):
        return CONTACT_EMAIL

    @Property(str, constant=True)
    def projectUrl(self):
        return PROJECT_URL

    @Property(str, constant=True)
    def confirmationWord(self):
        from services.reset_service import CONFIRMATION_WORD

        return CONFIRMATION_WORD

    @Property(str, constant=True)
    def backupSuffix(self):
        return BACKUP_SUFFIX

    def _run(self, work, done, problem: str = "") -> None:
        """Like `_mutate`, but hands the result to `done` on success.

        `problem` replaces the general failure text when the error is not
        one the catalog can explain, such as a file that cannot be read.
        """
        if self._busy:
            return
        self._set_busy(True)
        self._set_notice("")

        def succeeded(result):
            self._set_busy(False)
            self._set_message("")
            done(result)
            self.saved.emit()

        def failed(error):
            from app.accounts import is_explained, user_message

            self._set_busy(False)
            text = user_message(error)
            if problem and not is_explained(error):
                text = say(problem)
            if not isinstance(error, ValueError):
                get_logger().exception(
                    "Ayar işlemi başarısız.",
                    exc_info=(type(error), error, error.__traceback__),
                )
            self._set_message(text)

        self._tasks.submit(
            "settings", lambda _cancel: work(),
            on_success=succeeded, on_error=failed, replace=False,
        )

    # -- password ------------------------------------------------------------
    @Slot(str, str, str)
    def changePassword(self, current, password, confirmation):
        def work():
            result = self._auth.change_password(current, password, confirmation)
            if not result.ok:
                raise FormError(result.message)
            return result

        def done(result):
            self._set_notice(result.message)
            self.passwordChanged.emit()

        self._run(work, done)

    # -- backup --------------------------------------------------------------
    @Slot(str, str, str)
    def createBackup(self, url, passphrase, confirmation):
        def work():
            from services.backup_service import create_backup

            if len(passphrase) < 12:
                raise FormError(say("The backup password must be at least 12 characters."))
            if passphrase != confirmation:
                raise FormError(say("The two backup passwords do not match."))
            destination = local_path(url, BACKUP_SUFFIX)
            create_backup(
                destination, passphrase,
                db_path=database.db.DB_NAME, config_path=self._store.path,
            )
            return destination

        self._run(work, lambda path: self._set_notice(
            say("Backup saved to {0}. Keep its password safe: without it the backup cannot be opened.", os.path.basename(path))
        ), UNWRITABLE)

    @Slot(str, str)
    def restoreBackup(self, url, passphrase):
        def work():
            from services.backup_service import restore_backup
            from utils.errors import HelyosferError

            path = local_path(url)
            try:
                restore_backup(
                    path, passphrase,
                    db_path=database.db.DB_NAME, config_path=self._store.path,
                )
            except (HelyosferError, ValueError, OSError) as error:
                get_logger().warning("Yedek geri yüklenemedi: %s", type(error).__name__)
                raise FormError(
                    say("This backup could not be restored. Check the backup "
                    "password and that the file is a Helyosfer backup.")
                ) from error

        self._run(work, lambda _result: self.restored.emit())

    # -- CSV -----------------------------------------------------------------
    @Slot(str)
    def exportCsv(self, url):
        def work():
            from services.migration_service import export_all_to_csv

            return export_all_to_csv(local_path(url, ".csv"))

        self._run(work, lambda result: self._set_notice(
            say("Exported {0} rows to {1}. The file is not encrypted; store it carefully.", result[1], os.path.basename(result[0]))
        ), UNWRITABLE)

    @Slot(str, int)
    def importCsv(self, url, account_id):
        def work():
            from services.migration_service import import_transactions_from_csv

            if account_id < 0:
                raise FormError(say("Choose the account the transactions belong to."))
            return import_transactions_from_csv(local_path(url), account_id)

        def done(result):
            imported, skipped, net, duplicates = result
            text = say("Imported {0} transactions", imported)
            if duplicates:
                text += say(", left out {0} that were already in the account", duplicates)
            if skipped:
                text += say(", skipped {0} rows that could not be read", skipped)
            sign = "−" if net < 0 else "+"
            self._set_notice(say("{0}. Net effect on the balance: {1}{2} ₺.", text, sign, format_amount(net)))
            self.dataChanged.emit()

        self._run(work, done, UNREADABLE_CSV)

    # -- reset ---------------------------------------------------------------
    @Slot(str)
    def resetAll(self, typed):
        def work():
            from services.reset_service import CONFIRMATION_WORD, reset_all_data

            if (typed or "").strip().upper() != CONFIRMATION_WORD:
                raise FormError(say("Type {0} to confirm.", CONFIRMATION_WORD))
            reset_all_data(self._store)

        def done(_result):
            self._auth.renewal_required = False
            self.wiped.emit()

        self._run(work, done)

