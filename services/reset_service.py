"""Erases every record and returns the profile to its first-run state."""

from __future__ import annotations

from database.db import managed_connection
from database.init_db import initialize_database

CONFIRMATION_WORD = "DELETE"


def reset_all_data(store) -> None:
    """Empties every table, rebuilds the defaults and forgets the password.

    Tables are emptied inside one transaction with foreign-key checks deferred
    to the commit: `sqlite_master` lists parents before children, so checking
    row by row would refuse the very first delete.

    The failed-attempt counter is removed with the credential it belonged to;
    otherwise a user who reset while locked out would set a new password and
    still be told to wait.
    """
    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("BEGIN")
        cursor.execute("PRAGMA defer_foreign_keys = ON")
        cursor.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
        for row in cursor.fetchall():
            safe_name = row["name"].replace('"', '""')
            cursor.execute(f'DELETE FROM "{safe_name}"')
        cursor.execute("DELETE FROM sqlite_sequence")
        conn.commit()
    initialize_database()

    for key in ("security", "security_throttle"):
        store.delete(key)

    from services.asset_service import invalidate_asset_data_cache
    from services.dashboard_service import invalidate_dashboard_cache

    invalidate_asset_data_cache()
    invalidate_dashboard_cache()
