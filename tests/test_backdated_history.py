"""Balances over time follow the dates of the transactions."""

import datetime
import os
import tempfile
import unittest
from unittest import mock


def _day(offset):
    return datetime.date.today() - datetime.timedelta(days=offset)


class BackdatedHistoryTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 60000.0)

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _add(self, kind, amount, offset, account=None):
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            account_id=account or self.account, amount=amount, transaction_type=kind,
            category="Maaş" if kind == "income" else "Taksi", description="x",
            transaction_date=f"{_day(offset).isoformat()} 09:30:00",
            detect_subscription=False,
        )

    def _balance(self, offset):
        from services.history_service import get_balance_at

        return get_balance_at(_day(offset).isoformat())["total_balance"]

    def test_a_transaction_entered_today_leaves_earlier_days_unknown(self):
        self._add("expense", 500.0, 0)
        self.assertEqual(self._balance(0), 59500.0)
        self.assertIsNone(self._balance(1))

    def test_a_back_dated_transaction_is_drawn_from_its_own_day(self):
        self._add("expense", 500.0, 200)
        self._add("income", 2000.0, 100)
        self.assertIsNone(self._balance(201))
        self.assertEqual(self._balance(200), 59500.0)
        self.assertEqual(self._balance(150), 59500.0)
        self.assertEqual(self._balance(100), 61500.0)
        self.assertEqual(self._balance(0), 61500.0)

    def test_an_older_entry_made_later_moves_the_start_back_again(self):
        self._add("expense", 500.0, 30)
        self.assertIsNone(self._balance(60))
        self._add("expense", 1000.0, 90)
        self.assertEqual(self._balance(90), 59000.0)
        self.assertEqual(self._balance(60), 59000.0)
        self.assertEqual(self._balance(30), 58500.0)

    def test_the_series_reaches_back_to_the_earliest_transaction(self):
        from services.dashboard_service import balance_series

        self.assertEqual(len(balance_series("1 Yıl")), 1)
        self._add("expense", 500.0, 300)
        series = balance_series("1 Yıl")
        self.assertGreater(len(series), 20)
        self.assertEqual(series[0]["balance"], 59500.0)
        self.assertEqual(series[-1]["balance"], 59500.0)

    def test_accounts_from_the_setup_day_move_back_together(self):
        from services.account_service import AccountService

        AccountService.create_account("Second", "checking", 10000.0)
        self._add("expense", 500.0, 50)
        self.assertEqual(self._balance(50), 69500.0)
        self.assertEqual(self._balance(1), 69500.0)
        self.assertEqual(self._balance(0), 69500.0)
        self._add("expense", 100.0, 80)
        self.assertEqual(self._balance(80), 69900.0)
        self.assertEqual(self._balance(50), 69400.0)

    def test_an_account_opened_later_keeps_its_own_opening_day(self):
        from database.db import get_connection
        from services.account_service import AccountService

        second = AccountService.create_account("Second", "checking", 10000.0)
        conn = get_connection()
        try:
            for account, offset in ((self.account, 30), (second, 10)):
                conn.execute(
                    "UPDATE balance_events SET ts = ? WHERE entity_id = ?"
                    " AND source = 'account_opened'",
                    (f"{_day(offset).isoformat()} 09:00:00", account),
                )
            conn.commit()
        finally:
            conn.close()

        self._add("expense", 500.0, 50)
        self.assertEqual(self._balance(50), 59500.0)
        self.assertEqual(self._balance(11), 59500.0)
        self.assertEqual(self._balance(10), 69500.0)
        self.assertEqual(self._balance(0), 69500.0)

    def test_the_current_balance_is_what_the_ledger_adds_up_to(self):
        from database.db import get_connection

        for kind, amount, offset in (("expense", 500.0, 200), ("income", 2000.0, 100),
                                     ("expense", 75.5, 0), ("expense", 10.0, 365)):
            self._add(kind, amount, offset)
        conn = get_connection()
        try:
            balance = conn.execute("SELECT SUM(balance) FROM accounts").fetchone()[0]
            ledger = conn.execute("SELECT SUM(delta) FROM balance_events").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(round(balance, 2), 61414.5)
        self.assertEqual(round(ledger, 2), 61414.5)
        self.assertEqual(self._balance(0), 61414.5)

    def test_snapshots_taken_without_the_entry_are_dropped(self):
        from database.db import get_connection
        from services.history_service import write_daily_snapshot

        write_daily_snapshot()
        self._add("expense", 500.0, 10)
        conn = get_connection()
        try:
            left = conn.execute("SELECT COUNT(*) FROM daily_balance_snapshot").fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(left, 0)
        self.assertEqual(self._balance(0), 59500.0)
        self.assertEqual(self._balance(5), 59500.0)


if __name__ == "__main__":
    unittest.main()
