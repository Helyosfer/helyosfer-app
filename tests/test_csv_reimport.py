"""Importing a CSV file leaves out what the account already holds."""

import os
import tempfile
import unittest
from unittest import mock


class CsvReimportTest(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self._folder.name, "finance.db")
        self._patch = mock.patch("database.db.DB_NAME", self.db_path)
        self._patch.start()
        from database.init_db import initialize_database
        from services.account_service import AccountService

        initialize_database()
        self.account = AccountService.create_account("Main", "checking", 10000.0)

    def tearDown(self):
        self._patch.stop()
        self._folder.cleanup()

    def _add(self, kind, amount, description, stamp):
        from services.transaction_service import TransactionService

        TransactionService.add_transaction(
            self.account, amount, kind, "Ma\u015f" if kind == "income" else "Taksi",
            description, transaction_date=stamp, detect_subscription=False)

    def _balance(self, account=None):
        from services.account_service import AccountService

        return AccountService.get_account(account or self.account)["balance"]

    def _export(self):
        from services.migration_service import export_all_to_csv

        return export_all_to_csv(os.path.join(self._folder.name, "rows.csv"))[0]

    def test_importing_an_export_into_the_same_account_adds_nothing(self):
        from services.migration_service import import_transactions_from_csv

        self._add("expense", 320.0, "Gece d\u00f6n\u00fc\u015f\u00fc", "2026-03-04 22:15:00")
        self._add("income", 45000.0, "Mart", "2026-03-01 09:00:00")
        path = self._export()
        before = self._balance()
        self.assertEqual(import_transactions_from_csv(path, self.account), (0, 0, 0.0, 2))
        self.assertEqual(self._balance(), before)

    def test_another_account_receives_every_row(self):
        from services.account_service import AccountService
        from services.migration_service import import_transactions_from_csv

        self._add("expense", 320.0, "Gece", "2026-03-04 22:15:00")
        self._add("income", 1000.0, "Mart", "2026-03-01 09:00:00")
        other = AccountService.create_account("Other", "checking", 0.0)
        self.assertEqual(
            import_transactions_from_csv(self._export(), other), (2, 0, 680.0, 0))
        self.assertEqual(self._balance(other), 680.0)

    def test_rows_that_repeat_inside_the_file_are_all_kept(self):
        from services.account_service import AccountService
        from services.migration_service import import_transactions_from_csv

        for _ in range(3):
            self._add("expense", 45.0, "Kahve", "2026-03-04 08:30:00")
        path = self._export()
        other = AccountService.create_account("Other", "checking", 1000.0)
        self.assertEqual(import_transactions_from_csv(path, other), (3, 0, -135.0, 0))
        self.assertEqual(import_transactions_from_csv(path, other), (0, 0, 0.0, 3))
        self.assertEqual(self._balance(other), 865.0)

    def test_only_the_new_rows_of_a_grown_file_come_in(self):
        import shutil

        from services.account_service import AccountService
        from services.migration_service import import_transactions_from_csv

        other = AccountService.create_account("Other", "checking", 1000.0)
        self._add("expense", 45.0, "Kahve", "2026-03-04 08:30:00")
        first = os.path.join(self._folder.name, "first.csv")
        shutil.copyfile(self._export(), first)
        self._add("expense", 60.0, "Simit", "2026-03-05 08:30:00")
        grown = self._export()

        self.assertEqual(import_transactions_from_csv(first, other), (1, 0, -45.0, 0))
        self.assertEqual(import_transactions_from_csv(grown, other), (1, 0, -60.0, 1))
        self.assertEqual(self._balance(other), 895.0)


if __name__ == "__main__":
    unittest.main()
