"""A purchase in installments, read the way the card's statements carry it."""

import datetime
import os
import tempfile
import unittest
from unittest import mock

from services.installment_service import billing_days
from tests.clock import Clock


def _days(*texts):
    return [datetime.date.fromisoformat(text) for text in texts]


class BillingDaysTest(unittest.TestCase):
    def test_the_first_statement_on_or_after_the_purchase_carries_the_first(self):
        bought = datetime.date(2025, 3, 9)
        self.assertEqual(
            billing_days(bought, 15, 3), _days("2025-03-15", "2025-04-15", "2025-05-15"))
        # Bought on the statement day itself, it is on that statement.
        self.assertEqual(billing_days(datetime.date(2025, 3, 15), 15, 1), _days("2025-03-15"))

    def test_a_statement_day_that_has_passed_moves_it_to_next_month(self):
        self.assertEqual(
            billing_days(datetime.date(2025, 3, 20), 15, 2), _days("2025-04-15", "2025-05-15"))
        self.assertEqual(
            billing_days(datetime.date(2025, 12, 20), 15, 2), _days("2026-01-15", "2026-02-15"))

    def test_a_day_a_month_does_not_have_falls_on_its_last(self):
        self.assertEqual(
            billing_days(datetime.date(2025, 1, 31), 31, 4),
            _days("2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"),
        )

    def test_without_a_statement_day_it_is_a_month_after_the_purchase(self):
        for statement_day in (None, 0, "", "x", 40):
            with self.subTest(statement_day=statement_day):
                self.assertEqual(
                    billing_days(datetime.date(2025, 1, 31), statement_day, 3),
                    _days("2025-02-28", "2025-03-31", "2025-04-30"),
                )

    def test_no_installments_means_no_days(self):
        self.assertEqual(billing_days(datetime.date(2025, 1, 31), 15, 0), [])


class CardInstallmentsTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        self.clock = Clock(datetime.datetime(2025, 3, 9, 10, 0))
        self.clock.__enter__()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.card = AccountService.create_account(
            "Card", "credit_card", 0.0, credit_limit=50000.0, statement_date=15)

    def tearDown(self):
        self.clock.__exit__(None, None, None)
        self._patch.stop()
        os.unlink(self.db_path)

    def _buy(self, amount, installments, text="Coat"):
        from database.db import get_connection
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            self.card, amount, "expense", "Kıyafet", text, installments=installments,
            detect_subscription=False,
        )
        conn = get_connection()
        try:
            return conn.execute("SELECT MAX(id) FROM transactions").fetchone()[0]
        finally:
            conn.close()

    def _plans(self):
        from services.installment_service import card_installments

        return [
            (plan["description"], plan["billed_installments"], plan["total_installments"],
             plan["monthly_amount"], plan["remaining_amount"], plan["next_date"].isoformat())
            for plan in card_installments(self.card)
        ]

    def _on(self, month, day, year=2025):
        self.clock.move_to(datetime.datetime(year, month, day, 10, 0))

    def test_installments_are_billed_as_the_statement_days_pass(self):
        self._buy(1200.0, 6)
        self.assertEqual(self._plans(), [("Coat", 0, 6, 200.0, 1200.0, "2025-03-15")])
        self._on(3, 14)
        self.assertEqual(self._plans()[0][1], 0)
        self._on(3, 15)
        self.assertEqual(self._plans(), [("Coat", 1, 6, 200.0, 1000.0, "2025-04-15")])
        # Left closed for months, it is still where the statements are.
        self._on(7, 20)
        self.assertEqual(self._plans(), [("Coat", 5, 6, 200.0, 200.0, "2025-08-15")])

    def test_a_plan_that_has_been_billed_in_full_is_no_longer_listed(self):
        self._buy(1200.0, 2)
        self._on(4, 14)
        self.assertEqual(len(self._plans()), 1)
        self._on(4, 15)
        self.assertEqual(self._plans(), [])

    def test_the_last_installment_carries_what_rounding_left(self):
        self._buy(1000.0, 3)
        self.assertEqual(self._plans(), [("Coat", 0, 3, 333.33, 1000.0, "2025-03-15")])
        self._on(4, 15)
        self.assertEqual(self._plans(), [("Coat", 2, 3, 333.33, 333.34, "2025-05-15")])

    def test_the_one_billed_soonest_comes_first(self):
        self._buy(600.0, 3, "Shoes")
        self._on(3, 20)
        self._buy(900.0, 3, "Bag")
        self.assertEqual(
            [(plan[0], plan[1], plan[5]) for plan in self._plans()],
            [("Bag", 0, "2025-04-15"), ("Shoes", 1, "2025-04-15")],
        )
        self._on(5, 16)
        self.assertEqual(
            [(plan[0], plan[1], plan[5]) for plan in self._plans()], [("Bag", 2, "2025-06-15")])

    def test_a_plan_names_its_purchase_and_goes_with_it(self):
        from services.installment_service import card_installments
        from services.transaction_edit_service import delete_transaction, update_transaction

        purchase = self._buy(1200.0, 6)
        self.assertEqual(card_installments(self.card)[0]["transaction_id"], purchase)
        # Changed, the purchase is still the one the plan belongs to.
        update_transaction(purchase, 1800.0, "Kıyafet", "Coat", "2025-03-02")
        plan = card_installments(self.card)[0]
        self.assertEqual(
            (plan["transaction_id"], plan["monthly_amount"], plan["next_date"].isoformat()),
            (purchase, 300.0, "2025-03-15"),
        )
        delete_transaction(purchase)
        self.assertEqual(card_installments(self.card), [])

    def test_a_single_payment_and_a_missing_card_have_no_plans(self):
        from services.installment_service import card_installments

        self._buy(500.0, None)
        self._buy(500.0, 1)
        self.assertEqual(self._plans(), [])
        self.assertEqual(card_installments(9999), [])


if __name__ == "__main__":
    unittest.main()
