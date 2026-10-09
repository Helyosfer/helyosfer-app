"""A CSV export must not deliver a formula to a spreadsheet.

THE MEASURED DEFECT: `export_all_to_csv` wrote the decrypted
description/category/asset name raw with `csv.writer`. Excel and LibreOffice
decide whether a cell is a formula by looking at its FIRST character; a cell
beginning with `=`, `+`, `-` or `@` (and with a line break or tab) is treated
as a FORMULA on opening, even if the file is pure data. If the user wrote
`=1+1` in a transaction description that is not Helyosfer's fault; but
delivering that value to a spreadsheet as a formula is.

THE ROUND-TRIP REQUIREMENT: the escaping must be reversible. Saying "I put an
apostrophe in front" is not enough -- text the user REALLY began with an
apostrophe (`'+SUM(A1)`, `''=x`) must also come back byte for byte from an
export/import round. That is why values beginning with an apostrophe are
escaped as well; on import exactly ONE apostrophe is stripped and the mapping
stays unambiguous.

NUMERIC COLUMNS ARE OUT OF SCOPE: the `tutar` and `miktar` columns are numbers
the application produced itself. Adding an apostrophe to them would stop them
being numbers in the spreadsheet and would break the one thing the user can do
with the file (take a total).

"""
import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from services.migration_service import (
    CSV_HEADER,
    escape_csv_text,
    export_all_to_csv,
    parse_transactions_csv,
    unescape_csv_text,
)


DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


class CsvEscapeContractTest(unittest.TestCase):
    """The pure escape/unescape contract -- it MUST be reversible."""

    ROUND_TRIP_CASES = [
        "=1+1",
        "=cmd|'/c calc'!A1",
        "+SUM(A1:A9)",
        "-2+3",
        "@SUM(1)",
        "'+SUM(A1:A9)",
        "''=x",
        "'''",
        "\tsekmeyle baslar",
        "\rsatir basi",
        "\nyeni satir",
        "Market alışverişi",
        "Kira - Ocak",
        "2026-01-15",
        "1500.50",
        "",
        "'",
    ]

    def test_escape_then_unescape_returns_the_original(self):
        for value in self.ROUND_TRIP_CASES:
            with self.subTest(value=repr(value)):
                self.assertEqual(unescape_csv_text(escape_csv_text(value)), value)

    def test_escaped_value_never_starts_with_a_formula_trigger(self):
        for value in self.ROUND_TRIP_CASES:
            with self.subTest(value=repr(value)):
                escaped = escape_csv_text(value)
                if escaped:
                    self.assertFalse(
                        escaped.startswith(DANGEROUS),
                        f"{value!r} -> {escaped!r} hâlâ formül olarak açılır",
                    )

    def test_safe_text_is_left_byte_for_byte_alone(self):
        """The escaping must be THE IDENTITY on harmless text; otherwise every cell is corrupted."""
        for value in ("Market", "Kira Ocak", "2026-01-15", "1500.50", "Ünlü Şirket"):
            with self.subTest(value=value):
                self.assertEqual(escape_csv_text(value), value)


class CsvExportInjectionTest(unittest.TestCase):
    """The REAL production path: database -> export_all_to_csv -> file."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "finance.db"
        self.export_path = root / "export.csv"
        self.key = os.urandom(32)

        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=self.key
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account_id = AccountService.create_account(
            "Dışa Aktarım Hesabı", "checking", initial_balance=100000
        )

    def _add(self, description, category="Market"):
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            self.account_id, 125.50, "expense", category, description
        )

    def _rows(self):
        with open(self.export_path, "r", newline="", encoding="utf-8-sig") as handle:
            return list(csv.reader(handle))

    def test_dangerous_description_is_not_exported_as_a_formula(self):
        self._add("=1+1")
        export_all_to_csv(str(self.export_path))
        rows = self._rows()
        self.assertEqual(rows[0], CSV_HEADER)
        cells = [cell for row in rows[1:] for cell in row]
        self.assertNotIn("=1+1", cells)
        for cell in cells:
            self.assertFalse(
                cell.startswith(DANGEROUS),
                f"{cell!r} elektronik tabloda formül olarak açılır",
            )

    def test_dangerous_category_and_asset_name_are_neutralised(self):
        from services.asset_purchase_service import AssetPurchaseService

        self._add("normal", category="@cmd")
        AssetPurchaseService.create_purchase(
            asset_name='=HYPERLINK("http://x")',
            asset_code="+GCF",
            asset_type="Hisse",
            quantity=2,
            purchase_price=10,
            account_id=self.account_id,
        )
        export_all_to_csv(str(self.export_path))
        for row in self._rows()[1:]:
            for cell in row:
                self.assertFalse(
                    cell.startswith(DANGEROUS),
                    f"{cell!r} elektronik tabloda formül olarak açılır",
                )

    def test_numeric_columns_stay_numeric(self):
        """The amount/quantity columns must not be corrupted with an apostrophe."""
        self._add("normal açıklama")
        export_all_to_csv(str(self.export_path))
        rows = self._rows()


        amount_index = CSV_HEADER.index("tutar")
        kind_index = CSV_HEADER.index("kayit_turu")
        islem = [r for r in rows[1:] if r[kind_index] == "islem"][0]
        self.assertEqual(float(islem[amount_index]), 125.50)

    def test_export_import_round_trip_restores_the_original_text(self):
        """An export -> parse round must give the user's original text back."""
        originals = ["=1+1", "'+SUM(A1:A9)", "''=x", "@cmd", "\tsekme", "Normal metin"]
        for text in originals:
            self._add(text)
        export_all_to_csv(str(self.export_path))
        records, skipped = parse_transactions_csv(str(self.export_path))
        self.assertEqual(skipped, 0)
        self.assertEqual(
            [r["description"] for r in records],
            [t.strip() for t in originals],
        )

    def test_third_party_csv_apostrophes_are_left_alone(self):
        """If it is not our format the escaping is not reversed; a foreign file is not corrupted."""
        foreign = Path(self.tempdir.name) / "foreign.csv"
        foreign.write_text(
            "tarih,tur,kategori,tutar,aciklama\n"
            "2026-01-15,gider,Market,100.00,'alintili aciklama\n",
            encoding="utf-8",
        )
        records, skipped = parse_transactions_csv(str(foreign))
        self.assertEqual(skipped, 0)
        self.assertEqual(records[0]["description"], "'alintili aciklama")


if __name__ == "__main__":
    unittest.main()
