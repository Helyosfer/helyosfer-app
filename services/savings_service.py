"""Savings Goals service.

The database layer of the "Savings" module in the new interface. Adding money
to a goal means ISOLATING that money from the main checking account:
accounts.balance decreases and the goal's current_amount increases within the
same SQL transaction -- the two are atomic in a single commit, and if it is
interrupted the rollback undoes both. Withdrawal is the inverse. This is NOT
an income/expense; no record is written to the transactions table (it must not
appear as spending in the charts), only the balance is isolated.

goal_name is stored AES-encrypted; the amounts are plain REAL (see the schema
note in init_db.py). status: 'aktif' -> 'tamamlandi' once the goal is reached,
and back to 'aktif' if a withdrawal drops below the target. Those status
values are the literal strings stored in the database.

"""

import uuid
from datetime import date

from database.db import (
    ACCOUNT,
    DEFAULT_ACCOUNT_ID,
    SAVINGS_GOAL,
    SECRET_KEY,
    current_account_balance,
    current_goal_amount,
    get_connection,
    record_balance_event,
)
from utils.crypto import encrypt, decrypt
from utils.errors import DecryptionError, KeyUnavailableError
from utils.financial_decimal import fiat

STATUS_ACTIVE = "aktif"
STATUS_COMPLETED = "tamamlandi"


IDENTITY_MISMATCH_MESSAGE = (
    "Bu hedef artık mevcut değil ya da değişmiş görünüyor; işlem güvenlik "
    "için durduruldu ve hiçbir para hareket etmedi. Lütfen ekranı yenileyip "
    "tekrar deneyin."
)


def _assert_identity(cursor, goal_id, goal_uid):
    """Proves that the numeric id and the durable identity point at the same row.

    FAIL-CLOSED, and it runs BEFORE any money moves. The numeric `id` can be
    reused after a restore (see database/init_db.py and
    tests/test_savings_identity_reuse_regression.py): on its own it cannot
    prove WHICH goal a user action meant. If `goal_uid` is supplied, the two
    have to agree.

    If `goal_uid` is None no verification is done -- a deliberate door for
    older callers that do not know the identity (service tests, maintenance
    scripts). The interface ALWAYS passes a UID; if a card record has no UID,
    the interface does not send the operation to the service at all.
    """
    if goal_uid is None:
        return
    cursor.execute(
        "SELECT 1 FROM savings_goals WHERE id = ? AND goal_uid = ?",
        (goal_id, str(goal_uid)),
    )
    if cursor.fetchone() is None:
        from utils.logging_config import get_logger
        get_logger().warning(
            "[KİMLİK] savings_goals id=%s ile verilen goal_uid eşleşmiyor; "
            "işlem reddedildi", goal_id,
        )
        raise ValueError(IDENTITY_MISMATCH_MESSAGE)


class SavingsService:

    @staticmethod
    def create_goal(goal_name, target_amount, target_date=None, current_amount=0.0,
                    color=None, auto_deposit=False, created_at=None,
                    goal_uid=None):
        """Opens a new savings goal; returns the goal's id.

        `goal_uid` is the DURABLE identity and is generated here -- because the
        numeric `id` can be reused after a restore (see the note in
        init_db.py), it cannot be trusted as an identity. A caller may supply
        a UID explicitly; only the migration engine does so, and there too the
        value is `uuid4()`.
        """
        target_amount = float(fiat(target_amount))
        current_amount = float(fiat(current_amount))
        if target_amount <= 0:
            raise ValueError("Hedef tutar 0'dan büyük olmalıdır")
        if current_amount < 0:
            raise ValueError("Birikim tutarı negatif olamaz")
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO savings_goals (goal_name, target_amount, current_amount,
                                           target_date, status, goal_uid, color,
                                           auto_deposit, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (encrypt(str(goal_name), SECRET_KEY), target_amount,
                  current_amount, target_date,
                  STATUS_COMPLETED
                  if fiat(current_amount) >= fiat(target_amount)
                  else STATUS_ACTIVE,
                  str(goal_uid or uuid.uuid4()), color,
                  1 if auto_deposit else 0,
                  created_at or date.today().isoformat()))
            goal_id = cursor.lastrowid


            record_balance_event(cursor, SAVINGS_GOAL, goal_id, current_amount, current_amount,
                                 "savings_goal_created")
            conn.commit()
            return goal_id
        finally:
            conn.close()

    @staticmethod
    def get_goals(only_active=False):
        """Returns the goals with decrypted names (a list of dicts)."""
        conn = get_connection()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM savings_goals"
            if only_active:
                query += f" WHERE status = '{STATUS_ACTIVE}'"
            cursor.execute(query + " ORDER BY id")
            rows = cursor.fetchall()
        finally:
            conn.close()

        goals = []
        for r in rows:
            try:
                name = decrypt(r["goal_name"], SECRET_KEY)
            except KeyUnavailableError:


                raise
            except (DecryptionError, ValueError, TypeError):
                from utils.logging_config import get_logger
                get_logger().exception(
                    "[VERİ BÜTÜNLÜĞÜ] savings_goals id=%s adı çözülemedi",
                    r["id"])
                name = "Bilinmeyen Hedef"
            goals.append(SavingsService._goal_dict(r, name))
        return goals

    @staticmethod
    def _goal_dict(row, name):
        """Converts a row into the single dictionary shape of the service contract.

        `get_goals` and `_get_goal_row` used to build this dictionary
        SEPARATELY; when new fields were added, updating one and forgetting the
        other meant the goal card losing its colour or date after an
        operation.
        """
        return {
            "id": row["id"],
            "goal_uid": row["goal_uid"],
            "goal_name": name,
            "target_amount": row["target_amount"],
            "current_amount": row["current_amount"],
            "target_date": row["target_date"],
            "status": row["status"],
            "color": row["color"],
            "auto_deposit": bool(row["auto_deposit"]),
            "created_at": row["created_at"],
        }

    @staticmethod
    def deposit_to_goal(goal_id, amount, account_id=DEFAULT_ACCOUNT_ID,
                       goal_uid=None, effective_at=None):
        """Transfers money from the main account into the goal (atomic isolation).

        The insufficient-balance guard was removed: the account may go
        negative. Returns the goal's current state (a dict).

        If `goal_uid` is supplied, identity verification happens BEFORE ANY
        MONEY MOVES and the operation is rejected on a mismatch.

        `effective_at` is the day the move belongs to. When that day has
        passed, the ledger carries it on that day: an automatic contribution
        is recorded when it was due, however late the application is opened.
        """
        from database.db import _extend_ledger_back, past_event_stamp

        amount = float(fiat(amount))
        if amount <= 0:
            raise ValueError("Aktarılacak tutar 0'dan büyük olmalıdır")
        stamp = past_event_stamp(effective_at)

        conn = get_connection()
        try:
            cursor = conn.cursor()
            _assert_identity(cursor, goal_id, goal_uid)

            cursor.execute(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                (amount, account_id),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                raise ValueError("Hesap güncellenemedi (hesap bulunamadı).")

            cursor.execute(
                f"UPDATE savings_goals SET current_amount = current_amount + ? "
                f"WHERE id = ? AND status != '{STATUS_COMPLETED}'",
                (amount, goal_id),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                raise ValueError("Hedef bulunamadı ya da zaten tamamlanmış")


            cursor.execute(
                f"UPDATE savings_goals SET status = '{STATUS_COMPLETED}' "
                f"WHERE id = ? AND ROUND(current_amount, 2) "
                f">= ROUND(target_amount, 2)",
                (goal_id,),
            )


            if stamp is None:
                account_now = current_account_balance(cursor, account_id)
                goal_now = current_goal_amount(cursor, goal_id)
            else:
                # What each stood at right after a past move is not known:
                # later changes are already part of what they hold today.
                _extend_ledger_back(cursor, account_id, stamp)
                account_now = goal_now = None
            record_balance_event(
                cursor, ACCOUNT, account_id, -amount, account_now,
                "savings_deposit", goal_id, ts=stamp,
            )
            record_balance_event(
                cursor, SAVINGS_GOAL, goal_id, amount, goal_now,
                "savings_deposit", account_id, ts=stamp,
            )

            conn.commit()
            return SavingsService._get_goal_row(cursor, goal_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def withdraw_from_goal(goal_id, amount, account_id=DEFAULT_ACCOUNT_ID,
                           goal_uid=None):
        """Returns money from the goal to the main account (the inverse of
        deposit, the same atomic pattern).

        The `goal_uid` contract is the same as in `deposit_to_goal`.
        """
        amount = float(fiat(amount))
        if amount <= 0:
            raise ValueError("Çekilecek tutar 0'dan büyük olmalıdır")

        conn = get_connection()
        try:
            cursor = conn.cursor()
            _assert_identity(cursor, goal_id, goal_uid)


            cursor.execute(
                "UPDATE savings_goals SET current_amount = current_amount - ? "
                "WHERE id = ? AND ROUND(current_amount, 2) >= ROUND(?, 2)",
                (amount, goal_id, amount),
            )
            if cursor.rowcount == 0:
                conn.rollback()
                raise ValueError("Hedefte bu kadar birikim yok")

            cursor.execute(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                (amount, account_id),
            )


            cursor.execute(
                f"UPDATE savings_goals SET status = '{STATUS_ACTIVE}' "
                f"WHERE id = ? AND ROUND(current_amount, 2) "
                f"< ROUND(target_amount, 2)",
                (goal_id,),
            )


            record_balance_event(
                cursor, SAVINGS_GOAL, goal_id, -amount,
                current_goal_amount(cursor, goal_id),
                "savings_withdraw", account_id,
            )
            record_balance_event(
                cursor, ACCOUNT, account_id, amount,
                current_account_balance(cursor, account_id),
                "savings_withdraw", goal_id,
            )

            conn.commit()
            return SavingsService._get_goal_row(cursor, goal_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _get_goal_row(cursor, goal_id):
        """Reads a single goal with its decrypted name over an open cursor."""
        cursor.execute("SELECT * FROM savings_goals WHERE id = ?", (goal_id,))
        r = cursor.fetchone()
        if not r:
            return None
        try:
            name = decrypt(r["goal_name"], SECRET_KEY)
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError):
            from utils.logging_config import get_logger
            get_logger().exception(
                "[VERİ BÜTÜNLÜĞÜ] savings_goals id=%s adı çözülemedi", goal_id)
            name = "Bilinmeyen Hedef"
        return SavingsService._goal_dict(r, name)

    @staticmethod
    def delete_goal(goal_id, account_id=DEFAULT_ACCOUNT_ID, refund=True,
                    goal_uid=None):
        """Deletes the goal atomically; transfers the balance to the checking
        account if requested.

        The `goal_uid` contract is the same as in `deposit_to_goal` -- deletion
        is the most expensive operation to get wrong on the wrong goal, so it
        is verified here too.
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            _assert_identity(cursor, goal_id, goal_uid)
            cursor.execute("SELECT current_amount FROM savings_goals WHERE id = ?", (goal_id,))
            row = cursor.fetchone()
            if not row:
                return False
            refund_amount = float(row["current_amount"] or 0.0)
            if refund and refund_amount > 0:
                if account_id is None:
                    raise ValueError("Bakiyenin aktarılacağı hesap seçilmelidir")
                cursor.execute(
                    """UPDATE accounts SET balance = balance + ?
                       WHERE id = ? AND account_type = 'checking'""",
                    (refund_amount, account_id),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Seçilen vadesiz hesap bulunamadı")

                record_balance_event(
                    cursor, ACCOUNT, account_id, refund_amount,
                    current_account_balance(cursor, account_id),
                    "savings_goal_deleted", goal_id,
                )


            record_balance_event(
                cursor, SAVINGS_GOAL, goal_id, -refund_amount, 0.0,
                "savings_goal_deleted" if refund else "savings_goal_discarded",
                account_id,
            )
            cursor.execute("DELETE FROM savings_goals WHERE id = ?", (goal_id,))
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
