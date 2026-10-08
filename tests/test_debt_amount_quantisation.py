"""Debt amounts must enter the ledger rounded to the kurus.

The values reaching `insert_debt` are typically CALCULATED: the loan calculator
produces the monthly instalment from
the annuity formula without rounding, and the total is derived as
`instalment * term`. In their raw form these are values with sixteen
significant digits, such as 5493.320123592063.

This is not merely a cosmetic problem: the automatic instalment loop
writes a REAL transaction with the stored
`monthly_payment` and deducts it from the balance, so the raw amount reaches
both the transaction rows and the balance.

"""

import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from contextlib import closing
from unittest import mock


def _annuity_payment(principal, annual_rate_percent, months):
    """The loan calculator's annuity formula (KKDF+BSMV included)."""
    rate = (annual_rate_percent / 100) * (1 + 0.15 + 0.15)
    return principal * (rate * ((1 + rate) ** months)) / (((1 + rate) ** months) - 1)


class DebtAmountQuantisationTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database

        initialize_database()

    def tearDown(self):
        self._patch.stop()
        os.unlink(self.db_path)

    def _stored_amounts(self):
        from database.db import SECRET_KEY
        from utils.crypto import decrypt

        with closing(sqlite3.connect(self.db_path)) as conn:
            total, monthly = conn.execute(
                "SELECT total_amount, monthly_payment FROM active_debts"
            ).fetchone()
        return (
            Decimal(decrypt(str(total), SECRET_KEY)),
            Decimal(decrypt(str(monthly), SECRET_KEY)),
        )

    def test_a_calculated_loan_is_stored_at_kurus_precision(self):
        from database.db import insert_debt

        months = 36
        monthly = _annuity_payment(100_000.0, 3.29, months)
        total = monthly * months


        self.assertGreater(
            len(str(monthly).split(".")[1]), 2,
            "Hesaplanan taksit zaten yuvarlanmışsa vaka geçersiz",
        )

        insert_debt("Taşıt Kredisi", total, monthly, months)
        stored_total, stored_monthly = self._stored_amounts()

        self.assertEqual(stored_monthly, Decimal("5493.32"))
        self.assertEqual(stored_total, Decimal("197759.52"))

        self.assertLessEqual(-stored_monthly.as_tuple().exponent, 2)
        self.assertLessEqual(-stored_total.as_tuple().exponent, 2)

    def test_the_ledger_entry_matches_what_the_screen_shows(self):
        """The stored instalment must be byte for byte the amount shown on screen.

        The automatic payment writes a transaction with this value every
        month; in its raw form the row showed as "5.493,32" on screen while
        holding 5493.320123592063 on disk.
        """
        from database.db import insert_debt

        monthly = _annuity_payment(100_000.0, 3.29, 36)
        insert_debt("Taşıt Kredisi", monthly * 36, monthly, 36)
        _, stored_monthly = self._stored_amounts()

        self.assertEqual(f"{stored_monthly:,.2f}", f"{monthly:,.2f}")
        self.assertEqual(str(stored_monthly), f"{monthly:.2f}")

    def test_already_round_amounts_are_untouched(self):
        """Manually entered round amounts must be left unchanged."""
        from database.db import insert_debt

        insert_debt("Elle Girilen", 12_000.0, 1_000.0, 12)
        stored_total, stored_monthly = self._stored_amounts()
        self.assertEqual(stored_total, Decimal("12000.00"))
        self.assertEqual(stored_monthly, Decimal("1000.00"))


if __name__ == "__main__":
    unittest.main()
