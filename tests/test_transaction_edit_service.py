"""Changing and removing a transaction keeps balance, ledger and row together."""

import datetime
import os
import tempfile
import unittest
from unittest import mock


def _day(offset):
    return (datetime.date.today() - datetime.timedelta(days=offset)).isoformat()


class TransactionEditServiceTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 10000.0)

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    # -- helpers -------------------------------------------------------------
    def _add(self, kind="expense", amount=500.0, offset=0, account=None, category=None,
             installments=None):
        from database.db import get_connection
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            account_id=account or self.account, amount=amount, transaction_type=kind,
            category=category or ("Maaş" if kind == "income" else "Taksi"),
            description="Not", transaction_date=f"{_day(offset)} 09:30:00",
            installments=installments, detect_subscription=False,
        )
        conn = get_connection()
        try:
            return conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0]
        finally:
            conn.close()

    def _numbers(self):
        """(account balance, ledger total, transaction count)."""
        from database.db import get_connection

        conn = get_connection()
        try:
            balance = conn.execute(
                "SELECT balance FROM accounts WHERE id = ?", (self.account,)).fetchone()[0]
            ledger = conn.execute(
                "SELECT SUM(delta) FROM balance_events WHERE entity_id = ?",
                (self.account,)).fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        finally:
            conn.close()
        return round(balance, 2), round(ledger, 2), count

    def _balance_at(self, offset):
        from services.history_service import get_balance_at

        return get_balance_at(_day(offset))["total_balance"]

    # -- reading -------------------------------------------------------------
    def test_a_plain_transaction_is_read_back_unlocked(self):
        from services.transaction_edit_service import get_transaction

        found = get_transaction(self._add(amount=1250.5, offset=3))
        self.assertEqual(
            (found["amount"], found["type"], found["category"], found["description"],
             found["date"], found["locked"]),
            (1250.5, "expense", "Taksi", "Not", f"{_day(3)} 09:30:00", ""),
        )

    def test_a_missing_transaction_is_refused(self):
        from services.transaction_edit_service import NOT_FOUND, get_transaction

        with self.assertRaises(ValueError) as caught:
            get_transaction(999)
        self.assertEqual(str(caught.exception), NOT_FOUND)

    # -- removing ------------------------------------------------------------
    def test_removing_an_expense_gives_the_money_back(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0)
        self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))
        delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_removing_an_income_takes_it_out(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add("income", 2000.0)
        delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    def test_removing_a_past_transaction_clears_it_from_that_day_on(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0, offset=40)
        self.assertEqual(self._balance_at(20), 9500.0)
        delete_transaction(tx)
        self.assertEqual(self._balance_at(40), 10000.0)
        self.assertEqual(self._balance_at(20), 10000.0)
        self.assertEqual(self._balance_at(0), 10000.0)

    def test_removing_twice_is_refused_and_changes_nothing(self):
        from services.transaction_edit_service import delete_transaction

        tx = self._add(amount=500.0)
        delete_transaction(tx)
        with self.assertRaises(ValueError):
            delete_transaction(tx)
        self.assertEqual(self._numbers(), (10000.0, 10000.0, 0))

    # -- changing ------------------------------------------------------------
    def test_changing_the_amount_moves_the_balance_by_the_difference(self):
        from services.transaction_edit_service import get_transaction, update_transaction

        tx = self._add(amount=500.0)
        update_transaction(tx, 800.0, "Süpermarket", "Yeni not", _day(0))
        self.assertEqual(self._numbers(), (9200.0, 9200.0, 1))
        found = get_transaction(tx)
        self.assertEqual(
            (found["amount"], found["category"], found["description"]),
            (800.0, "Süpermarket", "Yeni not"),
        )
        self.assertEqual(found["date"], f"{_day(0)} 09:30:00")

    def test_moving_the_date_back_redraws_the_days_between(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0, offset=10)
        update_transaction(tx, 500.0, "Taksi", "Not", _day(60))
        self.assertEqual(self._balance_at(60), 9500.0)
        self.assertEqual(self._balance_at(30), 9500.0)
        self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))

    def test_moving_the_date_forward_frees_the_days_before(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0, offset=60)
        update_transaction(tx, 500.0, "Taksi", "Not", _day(10))
        self.assertEqual(self._balance_at(30), 10000.0)
        self.assertEqual(self._balance_at(10), 9500.0)

    def test_bad_changes_are_refused_and_change_nothing(self):
        from services.transaction_edit_service import update_transaction

        tx = self._add(amount=500.0)
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        for amount, category, date in (
            (0, "Taksi", _day(0)), (-5, "Taksi", _day(0)), (float("nan"), "Taksi", _day(0)),
            (500.0, "Maaş", _day(0)), (500.0, "Yok Böyle", _day(0)), (500.0, "Kredi Taksiti", _day(0)),
            (500.0, "Taksi", tomorrow), (500.0, "Taksi", "dün"),
        ):
            with self.subTest(amount=amount, category=category, date=date):
                with self.assertRaises(ValueError):
                    update_transaction(tx, amount, category, "x", date)
                self.assertEqual(self._numbers(), (9500.0, 9500.0, 1))

    def test_a_card_change_counts_only_the_difference_against_the_limit(self):
        from services.account_service import AccountService
        from services.transaction_edit_service import update_transaction

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=1000.0)
        tx = self._add(amount=900.0, account=card)
        update_transaction(tx, 1000.0, "Taksi", "Not", _day(0))
        with self.assertRaises(ValueError):
            update_transaction(tx, 1000.01, "Taksi", "Not", _day(0))
        self.assertEqual(AccountService.get_account(card)["balance"], -1000.0)

    # -- locked records --------------------------------------------------------
    def test_records_the_application_wrote_are_locked(self):
        from services.transaction_edit_service import (
            INSTALLMENT, LINKED, PENDING, delete_transaction, get_transaction, update_transaction,
        )
        from services.account_service import AccountService

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=50000.0)
        cases = [
            (self._add(amount=100.0, category="Kredi Taksiti"), LINKED),
            (self._add(amount=1200.0, account=card, installments=6), INSTALLMENT),
            (self._add(amount=100.0, offset=-5), PENDING),
        ]
        AccountService.pay_credit_card_debt(card, self.account, 300.0)
        from database.db import get_connection

        conn = get_connection()
        try:
            for row in conn.execute("SELECT id FROM transactions ORDER BY id DESC LIMIT 2"):
                cases.append((row[0], LINKED))
        finally:
            conn.close()

        before = self._numbers()
        for tx, reason in cases:
            with self.subTest(tx=tx, reason=reason):
                self.assertEqual(get_transaction(tx)["locked"], reason)
                with self.assertRaises(ValueError):
                    delete_transaction(tx)
                with self.assertRaises(ValueError):
                    update_transaction(tx, 1.0, "Taksi", "x", _day(0))
        self.assertEqual(self._numbers(), before)


if __name__ == "__main__":
    unittest.main()
