"""Due items: pending transactions, automatic recurring payments, debt instalments."""

import datetime
import os
import tempfile
import unittest
from unittest import mock

from services.scheduled_service import due_debt_installments
from tests.fixtures import AccountFixtureMixin


def _debt(**overrides):
    debt = {
        "is_auto_pay": True, "total_installments": 12, "paid_installments": 2,
        "auto_pay_day": 10, "last_auto_pay_date": None,
    }
    debt.update(overrides)
    return debt


class DueDebtInstallmentsTest(unittest.TestCase):
    def test_nothing_before_the_pay_day(self):
        self.assertEqual(due_debt_installments(_debt(), datetime.date(2026, 3, 9)), 0)

    def test_one_on_the_pay_day(self):
        self.assertEqual(due_debt_installments(_debt(), datetime.date(2026, 3, 10)), 1)

    def test_never_twice_in_one_month(self):
        debt = _debt(last_auto_pay_date="2026-03")
        self.assertEqual(due_debt_installments(debt, datetime.date(2026, 3, 28)), 0)

    def test_missed_months_are_caught_up(self):
        debt = _debt(last_auto_pay_date="2025-12")
        self.assertEqual(due_debt_installments(debt, datetime.date(2026, 3, 10)), 3)

    def test_catching_up_never_exceeds_what_remains(self):
        debt = _debt(last_auto_pay_date="2025-01", paid_installments=10)
        self.assertEqual(due_debt_installments(debt, datetime.date(2026, 3, 10)), 2)

    def test_day_31_falls_on_the_last_day_of_a_short_month(self):
        debt = _debt(auto_pay_day=31)
        self.assertEqual(due_debt_installments(debt, datetime.date(2026, 2, 27)), 0)
        self.assertEqual(due_debt_installments(debt, datetime.date(2026, 2, 28)), 1)

    def test_manual_and_finished_debts_owe_nothing(self):
        day = datetime.date(2026, 3, 20)
        self.assertEqual(due_debt_installments(_debt(is_auto_pay=False), day), 0)
        self.assertEqual(due_debt_installments(_debt(paid_installments=12), day), 0)


class ProcessDueItemsTest(AccountFixtureMixin, unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database

        initialize_database()
        self.account_id = self.create_test_account(balance=50000.0)
        self.today = datetime.date.today()

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _balance(self):
        from services.account_service import AccountService

        return AccountService.get_account(self.account_id)["balance"]

    def _process(self, day=None):
        from services.scheduled_service import process_due_items

        return process_due_items(day or self.today)

    def test_an_empty_profile_changes_nothing(self):
        self.assertFalse(self._process())
        self.assertEqual(self._balance(), 50000.0)

    def test_a_due_automatic_payment_is_taken_once(self):
        from database.db import insert_recurring_payment

        insert_recurring_payment(
            "Kira", 30000.0, "Ev Kirası", "monthly", self.today.isoformat(), True,
            account_id=self.account_id,
        )
        self.assertTrue(self._process())
        self.assertEqual(self._balance(), 20000.0)
        self.assertFalse(self._process())
        self.assertEqual(self._balance(), 20000.0)

    def test_manual_and_future_payments_are_left_alone(self):
        from database.db import insert_recurring_payment

        tomorrow = (self.today + datetime.timedelta(days=1)).isoformat()
        insert_recurring_payment(
            "Elle", 100.0, "Ev Kirası", "monthly", self.today.isoformat(), False,
            account_id=self.account_id,
        )
        insert_recurring_payment(
            "Yarin", 100.0, "Ev Kirası", "monthly", tomorrow, True,
            account_id=self.account_id,
        )
        self.assertFalse(self._process())
        self.assertEqual(self._balance(), 50000.0)

    def test_a_due_debt_instalment_is_taken_once_a_month(self):
        from database.db import get_active_debts
        from services.debt_payment_service import DebtPaymentService

        DebtPaymentService.create_debt("Telefon", 1250.0, 6, True, 1)
        self.assertTrue(self._process())
        self.assertEqual(self._balance(), 48750.0)
        self.assertEqual(get_active_debts()[0]["paid_installments"], 1)
        self.assertFalse(self._process())
        self.assertEqual(self._balance(), 48750.0)

    def test_a_pending_transaction_is_applied_when_its_day_comes(self):
        from services.transaction_service import TransactionService

        due = self.today + datetime.timedelta(days=5)
        TransactionService.add_transaction(
            self.account_id, 400.0, "expense", "İnternet", "Fiber",
            transaction_date=f"{due.isoformat()} 10:00:00", detect_subscription=False,
        )
        self.assertEqual(self._balance(), 50000.0)
        self.assertEqual(len(TransactionService.get_pending_transactions()), 1)


if __name__ == "__main__":
    unittest.main()
