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


def list_categories():
    """Every category as {category, type, importance}, in stored order."""
    with managed_connection() as conn:
        rows = conn.execute(
            "SELECT name, type, IFNULL(importance, 'extra') FROM categories ORDER BY id"
        ).fetchall()
    return [{"category": row[0], "type": row[1], "importance": row[2]} for row in rows]


def add_category(name, category_type, essential=False):
    """Adds a category the user names. Names are unique regardless of case."""
    from services.search_service import normalize

    name = " ".join(str(name or "").split())
    if not name:
        raise ValueError("Kategori adı boş olamaz.")
    if len(name) > MAX_CATEGORY_NAME_LENGTH:
        raise ValueError("Kategori adı en fazla 40 karakter olabilir.")
    if category_type not in CATEGORY_TYPES:
        raise ValueError("Kategori türü geçersiz.")
    wanted = normalize(name)
    with managed_connection() as conn:
        existing = conn.execute("SELECT name FROM categories").fetchall()
        if any(normalize(row[0]) == wanted for row in existing):
            raise ValueError("Bu adda bir kategori zaten var.")
        conn.execute(
            "INSERT INTO categories(name, type, importance) VALUES(?,?,?)",
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
