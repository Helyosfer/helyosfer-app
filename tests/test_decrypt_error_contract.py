"""`decrypt()` now raises -- the callers' contract has to match.

BACKGROUND. `utils.crypto.decrypt()` once swallowed every error
internally and returned a placeholder string. The callers were accordingly
written to catch the `ValueError`/`TypeError` that came out when they handed
that placeholder to `float()`.

`decrypt()` is now fail-closed: a corrupt envelope, tampered ciphertext or
an unreachable key now raises a TYPED exception
(`IntegrityVerificationError` / `DecryptionError` / `KeyUnavailableError`).
NONE of these is a `ValueError` or a `TypeError` -- measured. So the old
`except (ValueError, TypeError)` blocks at the call sites DO NOT ENGAGE on a
real corruption, and the exception leaked somewhere indeterminate.

This file pins two contracts at once:

  1. PER-RECORD CORRUPTION is caught, logged, and the flow continues (one
     broken row does not bring down the whole list).
  2. If THE KEY IS UNREACHABLE the exception PROPAGATES. Swallowing that per
     row would present a total failure -- "nothing can be decrypted" -- as
     NORMAL DATA: "everything is 0.00 lira" / "everything is Unknown" -- silent
     and dangerous.

"""
import logging
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from utils.errors import FinancialDataIntegrityError, KeyUnavailableError


CORRUPT = "AEADv1:bu-gecerli-bir-zarf-degil"


class _LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)

    def messages(self):
        return [r.getMessage() for r in self.records]


class _ContractTestBase(unittest.TestCase):
    """The shared setup. It contains no test itself -- both test classes inherit
    it. Deriving the `AggregatePaths...` class directly from
    `DecryptErrorContractTest` ran the parent's tests A SECOND TIME (7 tests
    became 18); unittest collects inherited `test_*` methods too.
    """

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_patch = mock.patch("database.db.DB_NAME", self.db_path)
        self.db_patch.start()
        from database.init_db import initialize_database
        initialize_database()

        self.capture = _LogCapture()
        logging.getLogger("helysofer").addHandler(self.capture)

    def tearDown(self):
        logging.getLogger("helysofer").removeHandler(self.capture)
        self.db_patch.stop()
        os.unlink(self.db_path)

    def _sql(self, statement, params=()):
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(statement, params)
            conn.commit()

    def _corrupt_row(self, table, columns, extra_columns=None):
        """Writes into the given table a single row whose encrypted columns are CORRUPT."""
        values = {column: CORRUPT for column in columns}
        values.update(extra_columns or {})
        names = ", ".join(values)
        marks = ", ".join("?" for _ in values)
        self._sql(
            f"INSERT INTO {table} ({names}) VALUES ({marks})",
            tuple(values.values()),
        )

    def _corrupt_recurring(self):
        self._corrupt_row(
            "recurring_payments", ["name", "amount"],
            {"frequency": "monthly", "next_due_date": "2026-09-01",
             "transaction_type": "expense", "is_active": 1,
             "recurrence_day": 1, "auto_deduct": 0, "category": "Test"},
        )


class DecryptErrorContractTest(_ContractTestBase):


    def test_corrupt_savings_goal_is_caught_and_logged(self):
        from services.savings_service import SavingsService

        self._corrupt_row(
            "savings_goals", ["goal_name"],


            {"target_amount": 100.0, "current_amount": 0.0,
             "goal_uid": "bozuk-satir-uid-1"},
        )
        goals = SavingsService.get_goals()

        self.assertEqual(len(goals), 1, "bozuk satır listeyi düşürmemeli")
        self.assertEqual(goals[0]["goal_name"], "Bilinmeyen Hedef")
        self.assertTrue(
            any("VERİ BÜTÜNLÜĞÜ" in m for m in self.capture.messages()),
            "bozulma sessiz kalmamalı — eskiden hiç iz bırakmıyordu",
        )

    def test_corrupt_asset_history_row_is_caught_and_logged(self):
        from database.db import get_asset_transaction_history

        self._corrupt_row(
            "transactions", ["amount", "description"],
            {"account_id": 1, "type": "expense", "category": "Varlık Alımı",
             "transaction_date": "2026-08-01 10:00:00"},
        )
        rows = get_asset_transaction_history()

        self.assertEqual(len(rows), 1, "bozuk satır listeyi düşürmemeli")
        self.assertTrue(
            any("VERİ BÜTÜNLÜĞÜ" in m for m in self.capture.messages()))

    def test_corrupt_recurring_payment_is_caught_and_logged(self):
        from database.db import get_active_recurring_payments

        self._corrupt_row(
            "recurring_payments", ["name", "amount"],
            {"frequency": "monthly", "next_due_date": "2026-09-01",
             "transaction_type": "expense", "is_active": 1},
        )
        payments = get_active_recurring_payments()

        self.assertEqual(len(payments), 1)
        self.assertTrue(
            any("VERİ BÜTÜNLÜĞÜ" in m for m in self.capture.messages()))

    def test_corrupt_csv_export_field_is_caught_and_logged(self):
        from services.migration_service import export_all_to_csv

        self._corrupt_row(
            "transactions", ["amount", "description"],
            {"account_id": 1, "type": "expense", "category": "Test",
             "transaction_date": "2026-08-01 10:00:00"},
        )
        export_path = os.path.join(tempfile.mkdtemp(), "export.csv")
        path, count = export_all_to_csv(export_path)

        self.assertEqual(count, 1, "tek bozuk satır dışa aktarımı düşürmemeli")
        self.assertTrue(
            any("VERİ BÜTÜNLÜĞÜ" in m for m in self.capture.messages()))


    def _with_unavailable_key(self, module_path):
        """Make `decrypt()` behave as though it cannot reach the key.

        CAREFUL -- patching `utils.crypto.decrypt` IS INEFFECTIVE: the calling
        modules bind the name into THEIR OWN module namespace with
        `from utils.crypto import decrypt`, so changing the object at the
        source does not affect that binding. The patch has to be made on the
        module that USES decrypt (the first version fell into this trap and the
        test passed silently).
        """
        return mock.patch(
            f"{module_path}.decrypt",
            side_effect=KeyUnavailableError("anahtar erişilemiyor"),
        )

    def test_key_unavailable_propagates_from_savings(self):
        from services.savings_service import SavingsService

        self._corrupt_row(
            "savings_goals", ["goal_name"],


            {"target_amount": 100.0, "current_amount": 0.0,
             "goal_uid": "bozuk-satir-uid-1"},
        )
        with self._with_unavailable_key("services.savings_service"):
            with self.assertRaises(KeyUnavailableError):
                SavingsService.get_goals()

    def test_key_unavailable_propagates_from_asset_history(self):
        from database.db import get_asset_transaction_history

        self._corrupt_row(
            "transactions", ["amount", "description"],
            {"account_id": 1, "type": "expense", "category": "Varlık Alımı",
             "transaction_date": "2026-08-01 10:00:00"},
        )
        with self._with_unavailable_key("database.db"):
            with self.assertRaises(KeyUnavailableError):
                get_asset_transaction_history()

    def test_key_unavailable_does_not_produce_a_silently_empty_csv(self):
        """The most dangerous scenario: the user downloads a CSV that is EMPTY from
        start to finish and thinks they have lost their data. The error must be
        visible.
        """
        from services.migration_service import export_all_to_csv

        self._corrupt_row(
            "transactions", ["amount", "description"],
            {"account_id": 1, "type": "expense", "category": "Test",
             "transaction_date": "2026-08-01 10:00:00"},
        )
        export_path = os.path.join(tempfile.mkdtemp(), "export.csv")
        with self._with_unavailable_key("services.migration_service"):
            with self.assertRaises(KeyUnavailableError):
                export_all_to_csv(export_path)


class AggregatePathsRefuseToBeSilentlyWrongTest(_ContractTestBase):
    """An amount entering a TOTAL is not counted as 0.00 if it cannot be decrypted.

    The distinction is not "amount or text" but "is this value being summed". A
    single wrong row in a list is visible and correctable; the same 0.00 in a
    TOTAL silently produces a wrong chart/budget and the user cannot notice.
    The application already applied this policy (`financial_summary_service`
    and the dashboard's integrity-error state); the two paths that had
    remained inconsistent are aligned here.
    """

    def test_chart_data_refuses_a_corrupt_amount_instead_of_zeroing_it(self):
        from services.transaction_service import TransactionService

        self._corrupt_row(
            "transactions", ["amount", "description"],
            {"account_id": 1, "type": "expense", "category": "Test",
             "transaction_date": "2026-08-01 10:00:00"},
        )
        with self.assertRaises(FinancialDataIntegrityError):
            TransactionService.get_transactions_by_period("Hayat Boyu")

    def test_budget_reserve_refuses_a_corrupt_recurring_amount(self):
        from services.budget_service import get_reserved_recurring_items

        self._corrupt_recurring()
        with self.assertRaises(FinancialDataIntegrityError):
            get_reserved_recurring_items(9, 2026)

    def test_display_lists_still_render_the_same_corrupt_recurring_row(self):
        """The display lists must CARRY ON WORKING while the budget refuses.

        The same record feeds four display lists; breaking all of them would be
        far too heavy a price for fixing the wrong total.
        """
        from database.db import get_active_recurring_payments

        self._corrupt_recurring()
        payments = get_active_recurring_payments()

        self.assertEqual(len(payments), 1, "liste düşmemeli")
        self.assertEqual(payments[0]["name"], "Bilinmeyen Ödeme")
        self.assertFalse(
            payments[0]["amount_is_valid"],
            "bozuk tutar bayrakla işaretlenmeli — toplam alan taraf buna bakıyor",
        )

    def test_sound_recurring_row_is_flagged_valid_and_reserved(self):
        """A sound record must be unaffected -- the flag must not produce a false positive."""
        from database.db import insert_recurring_payment
        from services.budget_service import get_reserved_recurring_items

        insert_recurring_payment(
            "Netflix", 99.99, "Abonelik", "monthly", "2026-09-01",
            recurrence_day=1, auto_deduct=0,
        )
        items = get_reserved_recurring_items(9, 2026)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "Netflix")


if __name__ == "__main__":
    unittest.main()
