"""Path resolver for user data.

Resolves WHERE user data (finance.db, config JSON), cache (brand icons) and
log (crash.log) files are kept, via `platformdirs`. In a packaged Windows
installation the application's own install directory (under `Program Files`)
is usually read-only -- we no longer write there.

This module only RESOLVES PATHS and has no I/O side effects
(`ensure_exists=False`): merely importing it or calling these functions
creates no real directory -- which is why the test suite importing
`database.db` does not create folders in the developer's actual home
directory. Real directory creation happens on the side of the code that
ACTUALLY writes there first (see `database/db.py::get_connection`).

The one-time move from the old locations to the new one is done by
`migrate_legacy_path()`; the caller decides WHAT is moved (which file, when)
-- this module only provides the mechanics of a safe move when the source
exists and the target does not.

"""
import base64
import os
import shutil
import sys
from typing import cast

from platformdirs import PlatformDirs

APP_NAME = "Helysofer"


_PRE_RENAME_APP_NAME = base64.b64decode("Zmlub3Jh").decode("ascii")


LEGACY_CONFIG_FILENAME = f"{_PRE_RENAME_APP_NAME}_config.json"


LEGACY_CBC_PASSWORD = f"{_PRE_RENAME_APP_NAME}_secure_2026"


def _dirs() -> PlatformDirs:
    return PlatformDirs(appname=APP_NAME, appauthor=False, ensure_exists=False)


def resource_dir() -> str:
    """The directory where READ-ONLY resources packaged with the application
    (`assets/*`) actually live.

    A crash verified empirically on a real Windows installation: interface files and
    constants like `database/db.py::NETWORK_LOGOS` all used RELATIVE paths -- that is,
    they ASSUMED the working directory (`cwd`) was THE SAME as the install
    folder. That assumption holds in development (the application is run from
    the repository root) but is WRONG for a packaged `.exe` opened from the
    Start Menu/desktop shortcut or from an installer's post-install "Launch"
    step -- Windows does NOT GUARANTEE the working directory
    matches the install folder. The result: a real user installation crashed
    at startup with `FileNotFoundError`.

    `sys._MEIPASS` is the directory where PyInstaller ACTUALLY places the
    files embedded via `datas=[...]` (when packaged, with `sys.frozen` true)
    -- it MAY NOT BE the same directory as the `.exe` itself (PyInstaller 6.x
    uses an `_internal` subfolder by default). Trusting
    `__file__` or `os.getcwd()` would be WRONG here -- neither is reliable in
    a packaged build.
    """
    if getattr(sys, "frozen", False):


        return cast(str, getattr(sys, "_MEIPASS"))

    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


HOME_OVERRIDE_ENV = "HELYSOFER_HOME"


def _override_root() -> str | None:
    root = os.environ.get(HOME_OVERRIDE_ENV, "").strip()
    return root or None


def data_dir() -> str:
    """Persistent user data for the SQLite database and JSON config files."""
    root = _override_root()
    if root:
        return os.path.join(root, "data")
    return _dirs().user_data_dir


def cache_dir() -> str:
    """For regenerable/disposable files such as brand icons."""
    root = _override_root()
    if root:
        return os.path.join(root, "cache")
    return _dirs().user_cache_dir


def log_dir() -> str:
    """For crash.log."""
    root = _override_root()
    if root:
        return os.path.join(root, "logs")
    return _dirs().user_log_dir


def migrate_legacy_path(old_path: str, new_path: str) -> bool:
    """Moves the file at `old_path` to `new_path` and returns `True` --
    only if `old_path` really exists AND `new_path` does not yet. In every
    other case it does nothing and returns `False`: on a fresh installation
    there is no old file to move; if `new_path` already exists (from an
    earlier migration or any other reason) an old copy is never written over
    the user's CURRENT data. Idempotent -- safe to call repeatedly.
    """
    if os.path.exists(new_path) or not os.path.exists(old_path):
        return False
    new_dir = os.path.dirname(new_path)
    if new_dir:
        os.makedirs(new_dir, exist_ok=True)


    shutil.copy2(old_path, new_path)
    try:
        os.remove(old_path)
    except OSError:
        pass
    return True
