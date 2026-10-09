"""A fixed amount moved into a savings goal each month, on its own.

A goal can have one contribution: an amount, the account it comes from, and
the day of the month it is due. It is moved with everything else that has
fallen due, after sign-in, through the same service a manual move uses, so
the account, the goal and the ledger change together.

It is deliberately cautious with the user's money:

  * once a month at most, and a missed month is not made up for later --
    three months away must not empty an account on return;
  * never more than the goal still needs;
  * never from an account that does not hold the amount: that month is
    skipped and tried again on the next sign-in, until the month ends.
"""

from __future__ import annotations

import calendar
import datetime

from database.db import get_connection
from services.savings_service import STATUS_COMPLETED, SavingsService
from utils.financial_decimal import fiat

_TABLE = """
    CREATE TABLE IF NOT EXISTS savings_auto_contributions (
        goal_uid TEXT PRIMARY KEY,
        account_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        day INTEGER NOT NULL CHECK (day BETWEEN 1 AND 31),
        last_month TEXT
    )
"""


def ensure_table(cursor) -> None:
    cursor.execute(_TABLE)


def _connection():
    conn = get_connection()
    ensure_table(conn.cursor())
    return conn


def set_contribution(goal_uid, account_id, amount, day) -> None:
    """Sets, or replaces, the monthly contribution of a goal."""
    amount = float(fiat(amount))
    if amount <= 0:
        raise ValueError("Aktarılacak tutar 0'dan büyük olmalıdır")
    day = int(day)
    if not 1 <= day <= 31:
        raise ValueError("Ödeme günü 1 ile 31 arasında olmalıdır.")
    conn = _connection()
    try:
        goal = conn.execute(
            "SELECT status FROM savings_goals WHERE goal_uid = ?", (str(goal_uid),)
        ).fetchone()
        if goal is None or goal[0] == STATUS_COMPLETED:
            raise ValueError("Hedef bulunamadı ya da zaten tamamlanmış")
        account = conn.execute(
            "SELECT account_type FROM accounts WHERE id = ?", (int(account_id),)
        ).fetchone()
        if account is None or account[0] == "credit_card":
            raise ValueError("Otomatik birikim için bir vadesiz hesap seçin.")
        # Changing the plan never moves money for the month already handled.
        previous = conn.execute(
            "SELECT last_month FROM savings_auto_contributions WHERE goal_uid = ?",
            (str(goal_uid),),
        ).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO savings_auto_contributions"
            " (goal_uid, account_id, amount, day, last_month) VALUES (?, ?, ?, ?, ?)",
            (str(goal_uid), int(account_id), amount, day, previous[0] if previous else None),
        )
        conn.commit()
    finally:
        conn.close()


def clear_contribution(goal_uid) -> bool:
    conn = _connection()
    try:
        cursor = conn.execute(
            "DELETE FROM savings_auto_contributions WHERE goal_uid = ?", (str(goal_uid),)
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_contributions() -> dict[str, dict]:
    """Every contribution, by the goal's durable identity."""
    conn = _connection()
    try:
        rows = conn.execute(
            "SELECT goal_uid, account_id, amount, day, last_month"
            " FROM savings_auto_contributions"
        ).fetchall()
    finally:
        conn.close()
    return {
        row[0]: {"account_id": row[1], "amount": float(row[2]), "day": row[3],
                 "last_month": row[4]}
        for row in rows
    }


def is_due(contribution: dict, today: datetime.date) -> bool:
    """True from the contribution's day until the month ends, once."""
    if contribution.get("last_month") == today.strftime("%Y-%m"):
        return False
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.day >= min(int(contribution["day"]), last_day)


def _mark(goal_uid, month) -> None:
    conn = _connection()
    try:
        conn.execute(
            "UPDATE savings_auto_contributions SET last_month = ? WHERE goal_uid = ?",
            (month, goal_uid),
        )
        conn.commit()
    finally:
        conn.close()


def process_due_contributions(today: datetime.date | None = None) -> int:
    """Moves every contribution that is due; returns how many were moved.

    A plan whose goal is gone or complete is removed. One that fails is
    left for the caller's log and does not stop the others.
    """
    today = today or datetime.date.today()
    month = today.strftime("%Y-%m")
    plans = get_contributions()
    if not plans:
        return 0
    goals = {goal["goal_uid"]: goal for goal in SavingsService.get_goals()}
    moved = 0
    for goal_uid, plan in plans.items():
        goal = goals.get(goal_uid)
        if goal is None or goal["status"] == STATUS_COMPLETED:
            clear_contribution(goal_uid)
            continue
        if not is_due(plan, today):
            continue
        remaining = fiat(goal["target_amount"]) - fiat(goal["current_amount"])
        amount = min(fiat(plan["amount"]), remaining)
        if amount <= 0:
            clear_contribution(goal_uid)
            continue
        if _account_balance(plan["account_id"]) < amount:
            continue
        SavingsService.deposit_to_goal(
            goal["id"], float(amount), plan["account_id"], goal_uid=goal_uid)
        _mark(goal_uid, month)
        moved += 1
    return moved


def _account_balance(account_id):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT balance FROM accounts WHERE id = ?", (int(account_id),)
        ).fetchone()
    finally:
        conn.close()
    return fiat(row[0] or 0) if row else fiat(-1)
