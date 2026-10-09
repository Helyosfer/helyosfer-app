"""A check a packaged build runs on itself: `Helysofer.exe --check-package`.

Much of what the application depends on is loaded only when a feature is
first used: the PDF writer, the market-data libraries, the key store. A
package that left one of them out still starts and shows every screen, and
fails later, on the user's computer. This runs each of those paths once, on
throwaway files, and reports the first that breaks.
"""

from __future__ import annotations

import os
import sys
import tempfile


def _pdf(folder: str) -> None:
    from services.loan_report import write_loan_schedule_pdf
    from services.loan_service import calculate_loan

    result = calculate_loan(100000, 3.0, 12, bank_fees=True)
    path = write_loan_schedule_pdf(os.path.join(folder, "check.pdf"), result, principal=100000)
    with open(path, "rb") as stream:
        if stream.read(5) != b"%PDF-":
            raise RuntimeError("the schedule was not written as a PDF")


def _market_data(_folder: str) -> None:
    import numpy  # noqa: F401
    import pandas  # noqa: F401
    import requests  # noqa: F401
    import yfinance  # noqa: F401

    import services.asset_price_worker  # noqa: F401
    import services.price_providers  # noqa: F401


def _records(folder: str) -> None:
    """A profile from nothing: key, schema, an encrypted write and its read."""
    import database.db

    database.db.DB_NAME = os.path.join(folder, "finance.db")
    from database.init_db import initialize_database
    from services.account_service import AccountService
    from services.dashboard_service import recent_transactions
    from services.transaction_service import TransactionService

    initialize_database()
    account = AccountService.create_account("Check", "checking", 1000.0)
    TransactionService.add_transaction(
        account, 12.5, "expense", "Taksi", "check", detect_subscription=False)
    rows = recent_transactions()
    if len(rows) != 1 or not rows[0]["readable"] or float(rows[0]["amount"]) != 12.5:
        raise RuntimeError("a saved transaction did not read back")


def _backup(folder: str) -> None:
    import database.db
    from services.backup_service import create_backup
    from utils.config_store import ConfigStore

    config = os.path.join(folder, "config.json")
    ConfigStore(config).put("display", style="Dark")
    target = os.path.join(folder, "check.helysofer-backup")
    create_backup(target, "check-passphrase-2026", db_path=database.db.DB_NAME, config_path=config)
    if os.path.getsize(target) < 1000:
        raise RuntimeError("the backup file is empty")


def _password(_folder: str) -> None:
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    if not hasher.verify(hasher.hash("check"), "check"):
        raise RuntimeError("a password did not verify")


def _resources(_folder: str) -> None:
    from utils.app_paths import resource_dir

    root = resource_dir()
    for needed in (("app", "qml", "Main.qml"), ("assets", "icon.png")):
        if not os.path.exists(os.path.join(root, *needed)):
            raise RuntimeError("missing " + "/".join(needed))


CHECKS = (
    ("interface files", _resources),
    ("password hashing", _password),
    ("records and encryption", _records),
    ("backup", _backup),
    ("PDF schedule", _pdf),
    ("market-data libraries", _market_data),
)


def run() -> int:
    """Runs the checks in order and returns 0 when all of them pass.

    The first one that fails ends the run: its error is not caught, so the
    traceback reaches the caller and the exit code is not zero.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        # Nothing here may touch the real profile.
        os.environ["HELYSOFER_HOME"] = os.path.join(folder, "home")
        for name, check in CHECKS:
            print(f"checking {name}", file=sys.stderr, flush=True)
            check(folder)
    print("all checks passed", file=sys.stderr, flush=True)
    return 0
