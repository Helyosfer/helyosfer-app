"""A fixed amount moved into a savings goal each month, on its own.

A goal can have one contribution: an amount, the account it comes from, and
the day of the month it is due. It is moved with everything else that has
fallen due, after sign-in, through the same service a manual move uses, so
the account, the goal and the ledger change together.

It behaves as a standing order at a bank does, and is careful with the money:

  * once for every month, on its day. A month that passed while the
    application was closed is made up for and recorded on that day, like an
    automatic payment or installment;
  * the first one is the next time its day comes round, never one that had
    already gone by when the plan was set;
  * never more than the goal still needs;
  * never from an account that does not hold the amount: that month, and
    the ones after it, wait and are tried again on the next sign-in.
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


def _day_in(index: int, day: int) -> datetime.date:
    """The contribution's day in a month counted as year * 12 + month - 1."""
    year, month = index // 12, index % 12 + 1
    return datetime.date(year, month, min(int(day), calendar.monthrange(year, month)[1]))


def _settled_month(day, today: datetime.date | None = None) -> str:
    """The last month a plan set today has nothing to move for."""
    today = today or datetime.date.today()
    index = today.year * 12 + today.month - 1
    if today.day <= _day_in(index, day).day:
        index -= 1
    return f"{index // 12}-{index % 12 + 1:02d}"


def due_days(contribution: dict, today: datetime.date) -> list[datetime.date]:
    """The days a contribution is owed for, oldest first.

    One for every month whose day has come since the last one moved. Before
    this month's day the months before it still count, so a day late in the
    month is not lost when the application is opened after it.
    """
    day = int(contribution["day"])
    this_month = today.year * 12 + today.month - 1
    latest = this_month if today >= _day_in(this_month, day) else this_month - 1
    last = contribution.get("last_month")
    if last:
        year, month = (int(part) for part in str(last).split("-"))
        first = year * 12 + month
    else:
        # Nothing is known about earlier months; only this one can be owed.
        first = this_month
    return [_day_in(index, day) for index in range(first, latest + 1)]


def next_day(contribution: dict, today: datetime.date) -> datetime.date:
    """The day the next contribution falls on; one already owed comes first."""
    owed = due_days(contribution, today)
    if owed:
        return owed[0]
    last = contribution.get("last_month")
    if last:
        year, month = (int(part) for part in str(last).split("-"))
        index = year * 12 + month
    else:
        index = today.year * 12 + today.month - 1
    return _day_in(index, int(contribution["day"]))


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
        # A plan looks ahead only: the month whose day has gone by counts as
        # handled. Changing the plan never moves money for a month that
        # already was, so the later of the two stands.
        previous = conn.execute(
            "SELECT last_month FROM savings_auto_contributions WHERE goal_uid = ?",
            (str(goal_uid),),
        ).fetchone()
        handled = max(filter(None, (previous[0] if previous else None, _settled_month(day))))
        conn.execute(
            "INSERT OR REPLACE INTO savings_auto_contributions"
            " (goal_uid, account_id, amount, day, last_month) VALUES (?, ?, ?, ?, ?)",
            (str(goal_uid), int(account_id), amount, day, handled),
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
    """True while a month's contribution has not been moved yet."""
    return bool(due_days(contribution, today))


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

    Each month owed is moved on its own, on its day. A plan whose goal is
    gone or complete is removed. One that fails is left for the caller's log
    and does not stop the others.
    """
    today = today or datetime.date.today()
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
        saved = fiat(goal["current_amount"])
        for day in due_days(plan, today):
            amount = min(fiat(plan["amount"]), fiat(goal["target_amount"]) - saved)
            if amount <= 0:
                clear_contribution(goal_uid)
                break
            if _account_balance(plan["account_id"]) < amount:
                # This month waits, and so do the ones after it.
                break
            SavingsService.deposit_to_goal(
                goal["id"], float(amount), plan["account_id"], goal_uid=goal_uid,
                effective_at=f"{day.isoformat()} 12:00:00",
            )
            _mark(goal_uid, day.strftime("%Y-%m"))
            saved += amount
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
