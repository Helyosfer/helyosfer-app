"""Safely resolves a restore left half-finished, at application startup.

Recovery has to run before EVERYTHING that touches the database, key or
config, so it sits at its own boundary, free of any UI toolkit, and can be
called and tested directly.

THE REQUIRED ORDER at startup:

    run_startup_recovery()          <-- here
    the encryption key is loaded
    migrate_legacy_database_location()
    initialize_database()               the database opens, migrations run
    the config is read

If recovery does not finish before those steps, the application starts up on
a half generation: the database may come from one backup and the config from
a different generation.

When it fails, the UI shows `USER_MESSAGE` under `RECOVERY_FAILURE_TITLE` and
stops; the same fail-closed surface is used with `SCHEMA_TOO_NEW_TITLE` and
`DATA_INTEGRITY_TITLE`. Only these fixed texts reach the user -- never an
exception message, path, table name or financial value.
"""

from __future__ import annotations

from enum import Enum

from utils.errors import DataMigrationError


class RecoveryOutcome(str, Enum):
    """An explicit contract -- no silent `None` return."""

    NOT_REQUIRED = "not-required"
    COMPLETED = "completed"
    MANUAL_INTERVENTION_REQUIRED = "manual-intervention-required"


class StartupRecoveryError(DataMigrationError):
    """Recovery could not complete safely; normal startup MUST NOT CONTINUE.

    Derived from `DataMigrationError` so the existing error boundaries already
    recognise it, while still being catchable as a distinct type.
    """

    def __init__(self, message, *, outcome):
        super().__init__(message)
        self.outcome = outcome


USER_MESSAGE = (
    "Önceki bir geri yükleme işlemi yarıda kalmış ve otomatik olarak "
    "onarılamadı. Verileriniz olduğu gibi korundu; hiçbir dosyanın üzerine "
    "yazılmadı. Devam etmeden önce yedekleme/kurtarma belgelerine bakın."
)


RECOVERY_FAILURE_TITLE = "Geri yükleme tamamlanamadı"
SCHEMA_TOO_NEW_TITLE = "Veritabanı bu sürümden yeni"
DATA_INTEGRITY_TITLE = "Veritabanı doğrulanamadı"


def run_startup_recovery(db_path=None, *, config_path=None):
    """Rolls back a half-finished restore if there is one; otherwise does nothing.

    Returns: `(RecoveryOutcome, detail_dictionary)`.

    FAIL-CLOSED: raises `StartupRecoveryError` if the journal is corrupt,
    carries an unrecognised state, or an error occurs during the rollback. The
    caller MUST catch this and STOP startup -- looking at a corrupt journal and
    assuming "everything is fine" is worse than starting on a mixed profile.
    """
    from database.db import DB_NAME
    from services.backup_service import recover_interrupted_restore

    target_db = db_path or DB_NAME
    try:
        result = recover_interrupted_restore(
            db_path=target_db, config_path=config_path
        )
    except DataMigrationError as exc:
        raise StartupRecoveryError(
            USER_MESSAGE,
            outcome=RecoveryOutcome.MANUAL_INTERVENTION_REQUIRED,
        ) from exc
    except OSError as exc:

        raise StartupRecoveryError(
            USER_MESSAGE,
            outcome=RecoveryOutcome.MANUAL_INTERVENTION_REQUIRED,
        ) from exc

    if not result.get("recovered"):
        return RecoveryOutcome.NOT_REQUIRED, result

    from utils.logging_config import get_logger

    get_logger().warning(
        "Yarım kalmış geri yükleme açılışta onarıldı (state=%s).",
        result.get("state"),
    )
    return RecoveryOutcome.COMPLETED, result
