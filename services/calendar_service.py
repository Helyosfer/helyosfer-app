"""Month- and day-scoped transaction queries for the calendar view.

The same encryption constraint as in insights_service.py applies: `amount` and
`description` are AES-encrypted TEXT, so they cannot be aggregated or searched
in SQL. The month grid needs only the DAY and a COUNT (which can be counted in
SQL over the plain `transaction_date`); to decrypt a single day's transactions
the rows are fetched and decrypted in Python. The service is independent of
the interface.

"""
from database.db import COMPLETED_TX, SECRET_KEY, managed_connection
from utils.crypto import decrypt
from utils.errors import DecryptionError, KeyUnavailableError


def get_month_transaction_days(year, month):
    """Returns `{day: transaction_count}` -- which days the month grid marks."""
    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT CAST(strftime('%d', transaction_date) AS INTEGER) AS day,
                   COUNT(*) AS cnt
            FROM transactions
            WHERE strftime('%Y-%m', transaction_date) = ?
              AND {COMPLETED_TX}
            GROUP BY day
            """,
            (f"{int(year):04d}-{int(month):02d}",),
        )
        rows = cursor.fetchall()
    return {row["day"]: row["cnt"] for row in rows}


def get_day_transactions(date_obj):
    """Returns a given day's transactions, decrypted.

    Returns: [{type, category, amount, description, time}, ...] in ascending
    time order. An amount that cannot be decrypted falls back to 0.0 -- one
    broken row must not drop the whole day from the list (see the same pattern
    in update_metrics_and_goals).
    """
    with managed_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, type, category, amount, description,
                   strftime('%H:%M', transaction_date) AS time
            FROM transactions
            WHERE date(transaction_date) = ?
              AND {COMPLETED_TX}
            ORDER BY transaction_date ASC
            """,
            (date_obj.isoformat(),),
        )
        rows = cursor.fetchall()

    items = []
    for row in rows:
        try:
            amount = float(decrypt(str(row["amount"]), SECRET_KEY))
        except KeyUnavailableError:


            raise
        except (DecryptionError, ValueError, TypeError):


            from utils.logging_config import get_logger
            get_logger().exception(
                "[VERİ BÜTÜNLÜĞÜ] takvim işlemi (%s %s) tutarı çözülemedi",
                date_obj, row["time"])
            amount = 0.0
        try:
            description = (
                decrypt(str(row["description"]), SECRET_KEY)
                if row["description"] else ""
            )
        except KeyUnavailableError:
            raise
        except (DecryptionError, ValueError, TypeError):
            from utils.logging_config import get_logger
            get_logger().exception(
                "[VERİ BÜTÜNLÜĞÜ] takvim işlemi (%s %s) açıklaması çözülemedi",
                date_obj, row["time"])
            description = ""
        items.append({
            "id": row["id"],
            "type": row["type"],
            "category": row["category"] or "Diğer",
            "amount": amount,
            "description": description,
            "time": row["time"],
        })
    return items
