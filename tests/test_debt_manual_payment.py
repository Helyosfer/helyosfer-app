"""Manual instalment payment and debt creation.

The payment writes the debt's progress, the expense and the balance in one
commit; these tests pin that a refused payment leaves all three untouched.
"""

import os
import tempfile
import unittest
from unittest import mock

from tests.fixtures import AccountFixtureMixin


class DebtManualPaymentTest(AccountFixtureMixin, unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.debt_payment_service import DebtPaymentService

        initialize_database()
        self.service = DebtPaymentService
        self.account_id = self.create_test_account(balance=10000.0)
        self.service.create_debt("Telefon", 1250.0, 6)
        self.debt_id = self._debt()["id"]

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _debt(self):
        from database.db import get_active_debts

        debts = get_active_debts()
        return debts[0] if debts else None

    def _balance(self):
        from services.account_service import AccountService

        return AccountService.get_account(self.account_id)["balance"]

    def _transaction_count(self):
        from database.db import managed_connection

        with managed_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    def test_the_total_is_the_rounded_instalment_times_the_count(self):
        self.service.create_debt("Kredi", 5493.320123592063, 24)
        from database.db import get_active_debts

        loan = next(d for d in get_active_debts() if d["debt_name"] == "Kredi")
        self.assertEqual(loan["monthly_payment"], 5493.32)
        self.assertEqual(loan["total_amount"], 131839.68)

    def test_paying_instalments_moves_progress_money_and_ledger_together(self):
        paid = self.service.pay_manual(self.debt_id, self.account_id, 2)
        self.assertEqual(paid, 2500.0)
        self.assertEqual(self._debt()["paid_installments"], 2)
        self.assertEqual(self._balance(), 7500.0)
        self.assertEqual(self._transaction_count(), 1)

    def test_paying_everything_closes_the_debt(self):
        self.assertEqual(self.service.pay_manual(self.debt_id, self.account_id), 7500.0)
        self.assertIsNone(self._debt())
        self.assertEqual(self._balance(), 2500.0)

    def test_the_last_instalments_close_the_debt_too(self):
        self.service.pay_manual(self.debt_id, self.account_id, 6)
        self.assertIsNone(self._debt())

    def test_more_than_remains_is_refused_and_nothing_changes(self):
        with self.assertRaises(ValueError):
            self.service.pay_manual(self.debt_id, self.account_id, 7)
        with self.assertRaises(ValueError):
            self.service.pay_manual(self.debt_id, self.account_id, 0)
        self.assertEqual(self._debt()["paid_installments"], 0)
        self.assertEqual(self._balance(), 10000.0)
        self.assertEqual(self._transaction_count(), 0)

    def test_a_frozen_account_refuses_and_the_debt_is_not_marked_paid(self):
        from services.account_service import AccountService

        AccountService.set_card_frozen(self.account_id, True)
        with self.assertRaises(ValueError):
            self.service.pay_manual(self.debt_id, self.account_id, 1)
        self.assertEqual(self._debt()["paid_installments"], 0)
        self.assertEqual(self._transaction_count(), 0)

    def test_a_closed_debt_cannot_be_paid_again(self):
        self.service.pay_manual(self.debt_id, self.account_id)
        with self.assertRaises(ValueError):
            self.service.pay_manual(self.debt_id, self.account_id, 1)
        self.assertEqual(self._balance(), 2500.0)

    def test_invalid_debts_are_refused(self):
        for arguments in (("", 100, 3), ("X", 0, 3), ("X", 100, 0), ("X", 100, 601)):
            with self.subTest(arguments=arguments):
                with self.assertRaises(ValueError):
                    self.service.create_debt(*arguments)
        with self.assertRaises(ValueError):
            self.service.create_debt("X", 100, 3, True, 32)


if __name__ == "__main__":
    unittest.main()
