"""The recorded debt total must be the amount the ledger will really pay.

The automatic instalment loop writes a transaction of
`monthly_payment` once a month and closes the debt when the instalment COUNT is
full. If the recorded total is larger than `instalment x term`, that total is
never reached when the debt is marked "closed".

The calculator used to put the extra charges into the debt total as well. Those
charges never visit this ledger -- they have their own terms and are shown
separately in the payment table as `amount / term` -- so they created a balance
the monthly payment could never close.

The DISPLAYED total ("Total Repayment") keeps the extra charges; that really is
the cost of the loan. What is separated out is only the debt RECORD.

"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from decimal import Decimal
from unittest import mock

from utils.financial_decimal import fiat


class DebtTotalMatchesLedgerTest(unittest.TestCase):
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


    def _stored(self):
        from database.db import SECRET_KEY
        from utils.crypto import decrypt

        with closing(sqlite3.connect(self.db_path)) as conn:
            total, monthly, count = conn.execute(
                "SELECT total_amount, monthly_payment, total_installments "
                "FROM active_debts"
            ).fetchone()
        return (
            Decimal(decrypt(str(total), SECRET_KEY)),
            Decimal(decrypt(str(monthly), SECRET_KEY)),
            int(count),
        )


    def test_the_invariant_survives_both_rounding_orders(self):
        """The total must be derived from the ROUNDED instalment -- not from `emi * n`.

        `insert_debt` rounds the two fields to the kurus separately and the two
        orders do not give the same result: for emi=1.005 and n=3,
        `fiat(emi) * n` is 3.00 while `fiat(emi * n)` is 3.01. If the wrong
        order is chosen the recorded total is one kurus more than the sum of
        the instalments to be paid, and when the automatic payment closes the
        debt it appears not to have closed.

        This test does not go through the calculator; it exercises the
        invariant directly, because whether the annuity formula gives an `emi`
        that produces the divergence is a matter of chance.
        """
        from database.db import insert_debt

        insert_debt("Ayrışma", float(fiat(1.005) * 3), 1.005, 3)
        total, monthly, count = self._stored()

        self.assertEqual(monthly, Decimal("1.00"))
        self.assertEqual(total, Decimal("3.00"))
        self.assertEqual(total, monthly * count)


if __name__ == "__main__":
    unittest.main()
