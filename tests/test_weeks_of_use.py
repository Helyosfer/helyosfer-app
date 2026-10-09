"""Months of use, played through with a clock the test moves.

What settles by itself (pending transactions, automatic payments, automatic
debt installments) must leave the same books whether the application was
opened every day or left closed for weeks: the same records, on the days
they were due, and the same balance on every day in between.
"""

import datetime
import os
import tempfile
import unittest
from unittest import mock

from tests.clock import Clock

START = datetime.datetime(2025, 1, 20, 9, 30)
LAST_DAY = 156  # 2025-06-25

EVERY_DAY = list(range(LAST_DAY + 1))
# Opened a few days, twice on some, then left alone for weeks at a time.
NOW_AND_THEN = [0, 1, 2, 9, 9, 10, 38, 39, 95, 95, 96, LAST_DAY]


def _day(offset):
    return (START + datetime.timedelta(days=offset)).date()


def _monthly(first, count):
    """`count` monthly dates from `first`, kept on its day of the month."""
    import calendar

    days = []
    for step in range(count):
        index = first.year * 12 + first.month - 1 + step
        year, month = index // 12, index % 12 + 1
        days.append(datetime.date(year, month, min(first.day, calendar.monthrange(year, month)[1])))
    return days


# Everything the books must hold at the end: (day, account, signed amount).
RENT = [(day, "main", -9000.0) for day in _monthly(datetime.date(2025, 1, 31), 5)]
SALARY = [(day, "main", 30000.0) for day in _monthly(datetime.date(2025, 2, 1), 5)]
MUSIC = [(_day(4 + 7 * week), "card", -90.0) for week in range(22)]
LOAN = [(day, "bills", -1500.0) for day in _monthly(datetime.date(2025, 2, 15), 5)]
PENDING = [(_day(9), "main", -700.0), (_day(40), "main", 2500.0), (_day(75), "card", -1200.0)]
BY_HAND = [(_day(2), "main", -300.0), (_day(20), "main", -450.0), (_day(95), "main", 1000.0)]
EXPECTED = sorted(RENT + SALARY + MUSIC + LOAN + PENDING + BY_HAND)
OPENING = {"main": 80000.0, "bills": 20000.0, "card": 0.0}


class WeeksOfUseTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.clock = Clock(START)
        self.clock.__enter__()
        from database.init_db import initialize_database

        initialize_database()

    def tearDown(self):
        self.clock.__exit__(None, None, None)
        self._patch.stop()
        os.unlink(self.db_path)

    # -- the profile ---------------------------------------------------------
    def _set_up(self):
        from database.db import insert_recurring_payment
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService
        from services.transaction_service import TransactionService

        self.accounts = {
            "main": AccountService.create_account("Main", "checking", OPENING["main"]),
            "bills": AccountService.create_account("Bills", "checking", OPENING["bills"]),
            "card": AccountService.create_account("Card", "credit_card", 0.0, credit_limit=50000.0),
        }
        main, card = self.accounts["main"], self.accounts["card"]
        insert_recurring_payment(
            "Rent", 9000.0, "Ev Kirası", "monthly", "2025-01-31", True,
            account_id=main, recurrence_day=31,
        )
        insert_recurring_payment(
            "Salary", 30000.0, "Maaş", "monthly", "2025-02-01", True,
            account_id=main, recurrence_day=1, transaction_type="income",
        )
        insert_recurring_payment(
            "Music", 90.0, "Dijital Abonelik", "weekly", _day(4).isoformat(), True,
            account_id=card,
        )
        # Paid by hand, so never taken by itself.
        insert_recurring_payment(
            "Gym", 400.0, "Spor & Sağlık (Abonelik)", "monthly", "2025-02-05", False,
            account_id=main,
        )
        DebtPaymentService.create_debt(
            "Loan", 1500.0, 10, True, 15, auto_pay_account_id=self.accounts["bills"],
        )
        for day, account, amount in PENDING:
            TransactionService.add_transaction(
                self.accounts[account], abs(amount), "income" if amount > 0 else "expense",
                "Maaş" if amount > 0 else "Taksi", "Planned",
                transaction_date=f"{day.isoformat()} 10:00:00", detect_subscription=False,
            )

    def _by_hand(self, offset):
        """What the user types in on the days the application is open."""
        from services.transaction_service import TransactionService

        def add(amount, kind, category, dated):
            TransactionService.add_transaction(
                self.accounts["main"], amount, kind, category, "By hand",
                transaction_date=f"{_day(dated).isoformat()} 11:00:00",
                detect_subscription=False,
            )

        if offset == 2:
            add(300.0, "expense", "Taksi", 2)
        elif offset == 38:
            # Entered late, for a day that has passed.
            add(450.0, "expense", "Süpermarket", 20)
        elif offset == 95:
            add(1000.0, "income", "Maaş", 95)

    def _play(self, opened_on):
        from services.scheduled_service import process_due_items

        self._set_up()
        seen = set()
        for offset in opened_on:
            self.clock.move_to(START + datetime.timedelta(days=offset))
            process_due_items()
            if offset not in seen:
                self._by_hand(offset)
            seen.add(offset)

    # -- reading the books -----------------------------------------------------
    def _records(self):
        """Every completed record as (day, account, signed amount), in order."""
        from database.db import SECRET_KEY, get_connection
        from utils.crypto import decrypt

        names = {identifier: name for name, identifier in self.accounts.items()}
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT account_id, amount, type, transaction_date FROM transactions"
                " WHERE IFNULL(status, 'completed') = 'completed'").fetchall()
        finally:
            conn.close()
        return sorted(
            (
                datetime.date.fromisoformat(row["transaction_date"][:10]),
                names[row["account_id"]],
                float(decrypt(row["amount"], SECRET_KEY)) * (1 if row["type"] == "income" else -1),
            )
            for row in rows
        )

    def _balances(self):
        """{account: (balance, sum of its ledger)}"""
        from database.db import get_connection

        conn = get_connection()
        try:
            return {
                name: tuple(round(value, 2) for value in conn.execute(
                    "SELECT a.balance, (SELECT SUM(delta) FROM balance_events"
                    " WHERE entity_type = 'account' AND entity_id = a.id)"
                    " FROM accounts a WHERE a.id = ?", (identifier,)).fetchone())
                for name, identifier in self.accounts.items()
            }
        finally:
            conn.close()

    def _assert_the_books_are_right(self):
        from services.history_service import get_balance_at

        self.assertEqual(self._records(), EXPECTED)
        for name, (balance, ledger) in self._balances().items():
            expected = OPENING[name] + sum(a for _, account, a in EXPECTED if account == name)
            self.assertEqual((name, balance, ledger), (name, expected, expected))
        # The balance on every single day follows the dates of the records,
        # not the days the application happened to be open.
        total = sum(OPENING.values())
        for offset in range(LAST_DAY + 1):
            day = _day(offset)
            expected = total + sum(amount for dated, _, amount in EXPECTED if dated <= day)
            self.assertEqual(
                (day, get_balance_at(day.isoformat())["total_balance"]), (day, expected),
            )

    # -- the two ways of using it ----------------------------------------------
    def test_opened_every_day(self):
        self._play(EVERY_DAY)
        self._assert_the_books_are_right()

    def test_opened_now_and_then(self):
        self._play(NOW_AND_THEN)
        self._assert_the_books_are_right()

    def test_opening_again_on_the_same_day_changes_nothing(self):
        from services.scheduled_service import process_due_items

        self._play(NOW_AND_THEN)
        before = (self._records(), self._balances())
        self.assertFalse(process_due_items())
        self.assertFalse(process_due_items())
        self.assertEqual((self._records(), self._balances()), before)

    def test_a_payment_made_by_hand_is_never_taken_by_itself(self):
        from database.db import get_active_recurring_payments

        self._play(NOW_AND_THEN)
        gym = next(p for p in get_active_recurring_payments() if p["name"] == "Gym")
        self.assertEqual(gym["next_due_date"], "2025-02-05")

    def test_what_comes_next_is_one_period_after_the_last_one_taken(self):
        from database.db import get_active_debts, get_active_recurring_payments

        self._play(NOW_AND_THEN)
        due = {p["name"]: p["next_due_date"] for p in get_active_recurring_payments()}
        self.assertEqual(
            (due["Rent"], due["Salary"], due["Music"]),
            ("2025-06-30", "2025-07-01", _day(4 + 7 * 22).isoformat()),
        )
        loan = get_active_debts()[0]
        self.assertEqual(
            (loan["paid_installments"], loan["last_auto_pay_date"]), (5, "2025-06"),
        )


class AutomaticDebtPaymentTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.clock = Clock(START)
        self.clock.__enter__()
        from database.init_db import initialize_database

        initialize_database()

    def tearDown(self):
        self.clock.__exit__(None, None, None)
        self._patch.stop()
        os.unlink(self.db_path)

    def _open_on(self, year, month, day):
        from services.scheduled_service import process_due_items

        self.clock.move_to(datetime.datetime(year, month, day, 9, 30))
        return process_due_items()

    def _paid(self):
        from database.db import get_active_debts

        return get_active_debts()[0]["paid_installments"]

    def _balance(self, account):
        from services.account_service import AccountService

        return AccountService.get_account(account)["balance"]

    def test_the_first_installment_is_the_next_pay_day_not_one_that_has_passed(self):
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService

        main = AccountService.create_account("Main", "checking", 10000.0)
        # Made on the 20th with pay day 15: this month's day has gone by.
        DebtPaymentService.create_debt("Loan", 500.0, 6, True, 15, auto_pay_account_id=main)
        self.assertFalse(self._open_on(2025, 1, 20))
        self.assertFalse(self._open_on(2025, 2, 14))
        self.assertTrue(self._open_on(2025, 2, 15))
        self.assertEqual((self._paid(), self._balance(main)), (1, 9500.0))

    def test_a_pay_day_still_to_come_this_month_is_the_first(self):
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService

        main = AccountService.create_account("Main", "checking", 10000.0)
        DebtPaymentService.create_debt("Loan", 500.0, 6, True, 25, auto_pay_account_id=main)
        self.assertFalse(self._open_on(2025, 1, 24))
        self.assertTrue(self._open_on(2025, 1, 25))
        self.assertEqual(self._paid(), 1)

    def test_turning_it_back_on_does_not_take_the_months_it_was_off(self):
        from database.db import get_active_debts, update_debt_auto_pay
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService

        main = AccountService.create_account("Main", "checking", 10000.0)
        DebtPaymentService.create_debt("Loan", 500.0, 12, True, 15, auto_pay_account_id=main)
        self._open_on(2025, 2, 15)
        self._open_on(2025, 3, 15)
        self.assertEqual(self._paid(), 2)
        debt = get_active_debts()[0]["id"]
        update_debt_auto_pay(debt, False, 1)
        self.assertFalse(self._open_on(2025, 7, 20))
        update_debt_auto_pay(debt, True, 15, main)
        self.assertFalse(self._open_on(2025, 7, 21))
        self.assertEqual((self._paid(), self._balance(main)), (2, 9000.0))
        self.assertTrue(self._open_on(2025, 8, 15))
        self.assertEqual((self._paid(), self._balance(main)), (3, 8500.0))

    def test_it_leaves_the_chosen_account_and_never_a_card(self):
        from database.db import get_active_debts
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService

        # The oldest account is a card: the old rule would have charged it.
        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=5000.0)
        first = AccountService.create_account("First", "checking", 4000.0)
        chosen = AccountService.create_account("Chosen", "checking", 6000.0)
        DebtPaymentService.create_debt("Loan", 500.0, 12, True, 15, auto_pay_account_id=chosen)
        DebtPaymentService.create_debt("Phone", 100.0, 12, True, 15)
        self._open_on(2025, 2, 15)
        self.assertEqual(
            (self._balance(card), self._balance(first), self._balance(chosen)),
            (0.0, 3900.0, 5500.0),
        )
        self.assertEqual([d["paid_installments"] for d in get_active_debts()], [1, 1])

    def test_with_no_account_to_take_it_from_it_waits(self):
        from services.account_service import AccountService
        from services.debt_payment_service import DebtPaymentService

        card = AccountService.create_account("Card", "credit_card", 0.0, credit_limit=5000.0)
        DebtPaymentService.create_debt("Loan", 500.0, 12, True, 15)
        self.assertFalse(self._open_on(2025, 2, 15))
        self.assertEqual((self._paid(), self._balance(card)), (0, 0.0))
        # An account opened later is charged for what waited, on its days.
        main = AccountService.create_account("Main", "checking", 3000.0)
        self.assertTrue(self._open_on(2025, 3, 20))
        self.assertEqual((self._paid(), self._balance(main)), (2, 2000.0))


class ClockTest(unittest.TestCase):
    def test_the_real_clock_is_back_when_the_test_is_over(self):
        import sys

        import database.db as db

        with Clock(START):
            from datetime import date as inside

            self.assertEqual(inside.today(), START.date())
            self.assertEqual(db.datetime.now(), START)
        self.assertIs(sys.modules["datetime"], datetime)
        self.assertIs(db.datetime, datetime.datetime)
        self.assertEqual(datetime.date.today(), datetime.datetime.now().date())

    def test_a_new_day_is_announced_once(self):
        from app.controllers import AppController

        with Clock(START) as clock:
            controller = AppController(None)
            heard = []
            controller.dayChanged.connect(lambda: heard.append(clock.today))
            controller.checkDay()
            controller.checkDay()
            self.assertEqual(heard, [])
            clock.advance(1)
            controller.checkDay()
            controller.checkDay()
            self.assertEqual(heard, [_day(1)])


if __name__ == "__main__":
    unittest.main()
