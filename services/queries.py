"""Small, read-only query services.

Two services too small to justify a file each are gathered here:
CategoryService (formerly services/category_service.py) and DashboardService
(formerly screens/dashboard.py -- not a screen, a service sitting in the wrong
folder). The shim files at the old module paths were removed once every import
had been pointed here.

TransactionHistoryService also lived here once; it was removed when it had no
callers left (account-scoped queries are in services/account_service.py).

Note: these services return the amount/description columns undecrypted (still
encrypted); decryption is the caller's responsibility (see utils/crypto.py).

"""
from database.db import ACCOUNT, managed_connection


class CategoryService:

    @staticmethod
    def get_categories(category_type=None):
        """Fetches categories by type (income/expense); all of them if no type is given."""
        with managed_connection() as conn:
            if category_type:
                rows = conn.execute(
                    "SELECT id, name FROM categories WHERE type = ?",
                    (category_type,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, name FROM categories"
                ).fetchall()
        return rows


MAX_CATEGORY_NAME_LENGTH = 40
CATEGORY_TYPES = ("income", "expense")


# Every place a category is stored by name.
_CATEGORY_COLUMNS = (
    ("transactions", "category"),
    ("monthly_budget_plan", "category_name"),
    ("recurring_payments", "category"),
)


def list_categories():
    """Every category as {category, type, importance, custom, in_use}, in stored order."""
    with managed_connection() as conn:
        rows = conn.execute(
            "SELECT name, type, IFNULL(importance, 'extra'), custom FROM categories ORDER BY id"
        ).fetchall()
        used: set[str] = set()
        for table, column in _CATEGORY_COLUMNS:
            used.update(
                found[0] for found in conn.execute(
                    f"SELECT DISTINCT {column} FROM {table}"  # nosec B608
                ).fetchall()
            )
    return [
        {"category": row[0], "type": row[1], "importance": row[2], "custom": bool(row[3]),
         "in_use": row[0] in used}
        for row in rows
    ]


def _clean_category_name(name):
    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Kategori adı boş olamaz.")
    if len(name) > MAX_CATEGORY_NAME_LENGTH:
        raise ValueError("Kategori adı en fazla 40 karakter olabilir.")
    return name


def _own_category(conn, name):
    """The stored row of a category the user added; refuses anything else."""
    row = conn.execute(
        "SELECT id, name, custom FROM categories WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        raise ValueError("Kategori bulunamadı.")
    if not row[2]:
        raise ValueError("Hazır kategoriler değiştirilemez.")
    return row


def rename_category(name, new_name):
    """Renames a category the user added, everywhere it is used."""
    from services.search_service import normalize

    new_name = _clean_category_name(new_name)
    wanted = normalize(new_name)
    with managed_connection() as conn:
        row = _own_category(conn, name)
        others = conn.execute(
            "SELECT name FROM categories WHERE id != ?", (row[0],)
        ).fetchall()
        if any(normalize(other[0]) == wanted for other in others):
            raise ValueError("Bu adda bir kategori zaten var.")
        conn.execute("UPDATE categories SET name = ? WHERE id = ?", (new_name, row[0]))
        for table, column in _CATEGORY_COLUMNS:
            conn.execute(
                f"UPDATE {table} SET {column} = ? WHERE {column} = ?",  # nosec B608
                (new_name, name),
            )
        conn.commit()
    from services.asset_service import mark_financial_data_changed

    mark_financial_data_changed()
    return new_name


def delete_category(name, move_to=None):
    """Removes a category the user added.

    While something is filed under it, it can only go together with those
    records: `move_to` names the category of the same kind that takes them
    over. Without it a category in use is refused.
    """
    with managed_connection() as conn:
        row = _own_category(conn, name)
        used = any(
            conn.execute(
                f"SELECT 1 FROM {table} WHERE {column} = ? LIMIT 1", (name,)  # nosec B608
            ).fetchone() is not None
            for table, column in _CATEGORY_COLUMNS
        )
        if used and not move_to:
            raise ValueError(
                "Bu kategori kullanımda olduğu için silinemez. Yeniden adlandırabilirsiniz."
            )
        if used:
            from services.transaction_edit_service import SYSTEM_CATEGORIES

            kind = conn.execute(
                "SELECT type FROM categories WHERE id = ?", (row[0],)).fetchone()[0]
            target = conn.execute(
                "SELECT name FROM categories WHERE name = ? AND type = ?", (move_to, kind)
            ).fetchone()
            if target is None or move_to == name or move_to in SYSTEM_CATEGORIES:
                raise ValueError("Kayıtların taşınacağı kategori geçersiz.")
            for table, column in _CATEGORY_COLUMNS:
                conn.execute(
                    f"UPDATE {table} SET {column} = ? WHERE {column} = ?",  # nosec B608
                    (move_to, name),
                )
        conn.execute("DELETE FROM categories WHERE id = ?", (row[0],))
        conn.commit()
    if used:
        from services.asset_service import mark_financial_data_changed

        mark_financial_data_changed()
    return True


def add_category(name, category_type, essential=False):
    """Adds a category the user names. Names are unique regardless of case."""
    from services.search_service import normalize

    name = _clean_category_name(name)
    if category_type not in CATEGORY_TYPES:
        raise ValueError("Kategori türü geçersiz.")
    wanted = normalize(name)
    with managed_connection() as conn:
        existing = conn.execute("SELECT name FROM categories").fetchall()
        if any(normalize(row[0]) == wanted for row in existing):
            raise ValueError("Bu adda bir kategori zaten var.")
        conn.execute(
            "INSERT INTO categories(name, type, importance, custom) VALUES(?,?,?,1)",
            (name, category_type, "main" if essential else "extra"),
        )
        conn.commit()
    return name


def set_category_importance(name, essential):
    """Marks a category as essential ('main') or extra.

    The split decides which bucket its transactions fall into in the
    summaries, so every figure derived from them is aged.
    """
    with managed_connection() as conn:
        cursor = conn.execute(
            "UPDATE categories SET importance = ? WHERE name = ?",
            ("main" if essential else "extra", name),
        )
        conn.commit()
        changed = cursor.rowcount > 0
    if changed:
        from services.asset_service import mark_financial_data_changed

        mark_financial_data_changed()
    return changed


class DashboardService:

    @staticmethod
    def get_total_balance():
        with managed_connection() as conn:
            result = conn.execute(
                "SELECT SUM(balance) as total FROM accounts"
            ).fetchone()

        return round(result["total"] or 0, 2)

    @staticmethod
    def get_opening_baseline():
        """The (signed) sum of the accounts' opening balances.

        WHY: the "My Wallet" total on the home screen is fed from the
        transaction ledger (income - expense); an account's opening balance,
        however, is written straight to accounts.balance and recorded in
        balance_events as 'account_opened', and NEVER enters transactions. The
        result: the opening balance appeared under "My Cards" but not under
        "My Wallet" (a synchronisation bug).

        This sum supplies the opening base that was being left out. It is kept
        separate rather than written as a fake "income" transaction, so that
        pure cash-flow analyses -- the savings rate, the 50-30-20 health score
        and the ODE daily-income input -- are not inflated by opening
        balances.

        Every account has exactly ONE 'account_opened' event (create_account
        writes it; for older accounts with no opening line, init_db completes
        it idempotently), so the sum of deltas equals the signed sum of the
        opening balances. Because credit-card debt enters with a negative
        sign, this total is automatically reduced by the debt.
        """
        with managed_connection() as conn:
            result = conn.execute(
                "SELECT COALESCE(SUM(delta), 0) AS total FROM balance_events"
                " WHERE entity_type = ? AND source = 'account_opened'",
                (ACCOUNT,),
            ).fetchone()
        return round(result["total"] or 0.0, 2)
