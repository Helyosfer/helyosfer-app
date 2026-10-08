"""Headline figures for the home screen, computed without any interface code.

Amounts are encrypted TEXT, so nothing here can be summed in SQL: rows are
fetched, decrypted and totalled in Python through `summarize_transactions`,
which refuses to count an unreadable amount as zero.

The wallet total comes from account balances, not from replaying income and
expense rows: ledger moves that are not transactions (savings deposits, for
example) would otherwise make it drift from the accounts screen.
"""

from __future__ import annotations

import datetime
import sqlite3
import threading

from database.db import COMPLETED_TX, COMPLETED_TX_T, SECRET_KEY, managed_connection
from services.dashboard_period_service import (
    PERIOD_DAYS, calculate_balance_change, period_bounds,
)
from services.financial_summary_service import summarize_transactions
from utils.crypto import decrypt
from utils.errors import (
    DecryptionError, HelysoferError, KeyUnavailableError,
)
from utils.financial_decimal import decimal_from
from utils.logging_config import get_logger

DEFAULT_PERIOD = "Bugün"
MIN_SERIES_DAYS = 7
MAX_SERIES_POINTS = 30

_cache_lock = threading.Lock()
_cache: tuple | None = None


def invalidate_dashboard_cache() -> None:
    global _cache
    with _cache_lock:
        _cache = None


def compute_dashboard_metrics(filter_text: str = DEFAULT_PERIOD) -> dict:
    """Totals, the selected period's flow and the 30-day daily averages."""
    global _cache
    from services.asset_service import get_financial_data_revision
    from services.queries import DashboardService

    cache_key = (
        get_financial_data_revision(),
        filter_text,
        datetime.date.today().isoformat(),
    )
    with _cache_lock:
        if _cache is not None and _cache[0] == cache_key:
            return _cache[1]

    period_start, period_end = period_bounds(filter_text)
    with managed_connection() as conn:
        all_rows = conn.execute(f"""
            SELECT t.id, t.amount, t.type,
                   IFNULL(c.importance, 'extra') AS importance
            FROM transactions t
            LEFT JOIN categories c ON t.category = c.name
            WHERE {COMPLETED_TX_T}
        """).fetchall()
        if period_start is None:
            period_rows = conn.execute(
                f"SELECT id, amount, type, 'extra' AS importance "
                f"FROM transactions WHERE {COMPLETED_TX}"
            ).fetchall()
        else:
            period_rows = conn.execute(
                f"SELECT id, amount, type, 'extra' AS importance "
                f"FROM transactions WHERE date(transaction_date) BETWEEN ? AND ?"
                f" AND {COMPLETED_TX}",
                (period_start.isoformat(), period_end.isoformat()),
            ).fetchall()
        recent_rows = conn.execute(f"""
            SELECT id, type, amount, 'extra' AS importance
            FROM transactions
            WHERE date(transaction_date) >= date('now', '-30 days', 'localtime')
              AND {COMPLETED_TX}
        """).fetchall()

    summary = summarize_transactions(all_rows)
    period = summarize_transactions(period_rows)
    recent = summarize_transactions(recent_rows)
    total_balance = decimal_from(DashboardService.get_total_balance())

    try:
        change = calculate_balance_change(filter_text, total_balance, today=period_end)
    except (sqlite3.Error, HelysoferError, ValueError, ArithmeticError):
        # The balance history is optional for the headline figures.
        get_logger().exception("Dönem bakiye değişimi hesaplanamadı")
        change = {"nominal_change": None, "percentage": None}

    metrics = {
        "filter_text": filter_text,
        "total_income": summary.total_income,
        "total_expense": summary.total_expense,
        "total_balance": total_balance,
        "period_income": period.total_income,
        "period_expense": period.total_expense,
        "period_net": period.net,
        "balance_change": change["nominal_change"],
        "change_rate": change["percentage"],
        "projection_daily_income": recent.total_income / 30,
        "projection_daily_expense": recent.total_expense / 30,
    }
    with _cache_lock:
        _cache = (cache_key, metrics)
    return metrics


def recent_transactions(limit: int = 8) -> list[dict]:
    """The latest completed transactions, newest first.

    A row whose amount or description cannot be decrypted is still listed,
    marked `readable: False`, so one damaged record stays visible instead of
    silently vanishing. A missing key is different: nothing can be read, so
    it is raised.
    """
    with managed_connection() as conn:
        rows = conn.execute(
            f"SELECT id, amount, type, category, description, transaction_date "
            f"FROM transactions WHERE {COMPLETED_TX} "
            f"ORDER BY transaction_date DESC, id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()

    items = []
    for row in rows:
        readable = True
        amount = None
        description = ""
        try:
            amount = decimal_from(decrypt(row[1], SECRET_KEY))
            description = decrypt(row[4], SECRET_KEY) if row[4] else ""
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError, ArithmeticError):
            readable = False
        items.append({
            "id": row[0],
            "amount": amount,
            "type": row[2],
            "category": row[3] or "Diğer",
            "description": description,
            "date": str(row[5])[:10],
            "readable": readable,
        })
    return items


def balance_series(filter_text: str = DEFAULT_PERIOD, today=None) -> list[dict]:
    """Total balance at evenly spaced day ends across the selected period.

    Days before the ledger started have no data and are left out rather than
    drawn as zero. "Today" and "all time" are too short or unbounded to chart,
    so they fall back to a week and a year.
    """
    from services.history_service import get_balance_at

    end = today or datetime.date.today()
    days = max(PERIOD_DAYS.get(filter_text, 365), MIN_SERIES_DAYS)
    count = min(days, MAX_SERIES_POINTS)
    step = (days - 1) / (count - 1)
    offsets = sorted({round(index * step) for index in range(count)}, reverse=True)

    series = []
    for offset in offsets:
        day = end - datetime.timedelta(days=offset)
        balance = get_balance_at(day.isoformat())["total_balance"]
        if balance is not None:
            series.append({"date": day.isoformat(), "balance": float(balance)})
    return series
