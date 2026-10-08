"""The numeric validation of the CSV import.

The bug found in the audit: `parse_transactions_csv` parsed the amount with
`float(raw)` and only checked `amount <= 0`. BOTH `float("inf")` and
`float("nan")` parse without complaint in Python and BOTH PASS that check
(IEEE 754: every comparison made with nan is False, and inf is certainly not
<= 0). Once such a row is imported, `adjust_account_balance`'s
`balance = balance + ?` poisons the account permanently; the inf/nan then
spreads through EVERY subsequent `SUM(balance)`, corrupting every net worth
figure in the application.

The manual entry path was already protected against this class
(utils/formatters.py: canonical value + input filter); the same discipline had
never been applied to the CSV path.

"""
import os
import tempfile
import unittest

from services.migration_service import parse_transactions_csv

_HEADER = "tarih,tur,kategori,tutar,aciklama\n"


class CsvAmountValidationTest(unittest.TestCase):
    def _parse(self, amount_text):
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        self.addCleanup(os.unlink, path)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_HEADER)
            f.write(f"2026-01-15,gider,Market,{amount_text},Test\n")
        return parse_transactions_csv(path)

    def test_infinity_is_rejected(self):
        records, skipped = self._parse("inf")
        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)

    def test_negative_infinity_is_rejected(self):
        records, skipped = self._parse("-inf")
        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)

    def test_nan_is_rejected(self):
        records, skipped = self._parse("nan")
        self.assertEqual(records, [])
        self.assertEqual(skipped, 1)

    def test_capitalised_infinity_spelling_is_rejected(self):
        """float() also accepts the spellings 'Infinity' and 'NaN'."""
        for spelling in ("Infinity", "NaN", "INF"):
            with self.subTest(spelling=spelling):
                records, skipped = self._parse(spelling)
                self.assertEqual(records, [], f"{spelling} kabul edildi")
                self.assertEqual(skipped, 1)

    def test_ordinary_amount_still_imports(self):
        """The fix must not block valid amounts."""
        records, skipped = self._parse("1500.50")
        self.assertEqual(skipped, 0)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["amount"], 1500.50)

    def test_turkish_thousands_format_still_imports(self):


        records, skipped = self._parse('"1.234,56"')
        self.assertEqual(skipped, 0)
        self.assertEqual(records[0]["amount"], 1234.56)

    def test_zero_and_negative_are_still_rejected(self):
        for value in ("0", "-5"):
            with self.subTest(value=value):
                records, skipped = self._parse(value)
                self.assertEqual(records, [])
                self.assertEqual(skipped, 1)


if __name__ == "__main__":
    unittest.main()
