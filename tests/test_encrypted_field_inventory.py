"""Is `ENCRYPTED_FIELDS` bound to the real schema -- or only to itself?

WHY THIS TEST EXISTS: `ENCRYPTED_FIELDS` is the single source for three places
-- backup (`backup_service`), migration from the old format
(`crypto_migration_service`) and key verification (`key_recovery_service`). If a
column is not in that map it does not enter the backup, is not migrated, and
does not appear in the key verification.

The existing gate (`test_crypto_migration_coverage`) verifies the map against
the schema IT BUILDS ITSELF:

    self.assertEqual(set(inserts), set(ENCRYPTED_FIELDS))

That warns when something is added to the map -- that direction is covered. But
the map and the test only hold EACH OTHER; neither is bound to the real schema.
So if an encrypted column is added to the real schema and not to the map,
nothing catches it and that column silently stays out of the backup.

This test closes the gap: it runs the application's OWN write paths and scans
every table that appears on disk, column by column, verifying that every column
carrying encrypted data is in the map. Because encrypted values begin with
`AEADv1:`, the detection rests on the data itself rather than on a guess.

"""

import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

AEAD_PREFIX = "AEADv1:"


class EncryptedFieldInventoryTest(unittest.TestCase):
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

    def _exercise_every_encrypting_write_path(self):
        """Really runs the production paths that produce encrypted data."""
        from database.db import insert_debt
        from services.account_service import AccountService
        from services.asset_purchase_service import AssetPurchaseService
        from services.recurring_service import (
            register_subscription_from_transaction,
        )
        from services.savings_service import SavingsService
        from services.transaction_service import TransactionService

        account_id = AccountService.create_account(
            "Vadesiz", "checking", initial_balance=50_000.0
        )
        card_id = AccountService.create_account(
            "Kart", "credit_card", credit_limit=50_000.0
        )

        # transactions (amount, description)
        TransactionService.add_transaction(
            account_id, 250.0, "expense", "Market", "Haftalık alışveriş",
            transaction_date="2026-08-01 10:00:00",
        )
        # installment_plans (description, total_amount, monthly_amount)
        TransactionService.add_transaction(
            card_id, 1200.0, "expense", "Elektronik", "Telefon",
            transaction_date="2026-08-01 11:00:00", installments=6,
        )
        # active_assets (purchase_price, quantity)
        AssetPurchaseService.create_purchase(
            asset_name="Gram Altın", asset_code="GC=F", asset_type="Altın",
            purchase_price=2890.45, quantity=2.0, account_id=account_id,
        )
        # active_debts (debt_name, total_amount, monthly_payment)
        insert_debt("Araç Kredisi", 60_000.0, 5_000.0, 12)


        register_subscription_from_transaction(
            card_id, 149.90, "Dijital Platformlar", "Streaming",
            transaction_date="2026-08-01 12:00:00", is_credit_card=True,
        )
        # savings_goals (goal_name)
        SavingsService.create_goal("Tatil", 10_000.0)


        import json as _json
        from pathlib import Path as _Path
        from services.savings_migration import run_savings_migration

        legacy_json = _Path(self.db_path).with_name("savings_goals.json")
        legacy_json.write_text(
            _json.dumps({"goals": {"data": [

                {"id": 4242, "name": "Kayıp Fon", "target": 9000.0,
                 "current": 4500.0},
            ]}}),
            encoding="utf-8",
        )
        run_savings_migration(
            json_path=legacy_json, db_path=self.db_path
        )

    def _columns_holding_encrypted_data(self):
        """The (table, column) pairs really carrying AEAD data on disk."""
        found = set()
        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = [
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name NOT LIKE 'sqlite_%'"
                )
            ]
            for table in tables:
                columns = [
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                ]
                for row in conn.execute(f"SELECT * FROM {table}"):
                    for column, value in zip(columns, row):
                        if isinstance(value, str) and value.startswith(AEAD_PREFIX):
                            found.add((table, column))
        return found

    def test_setup_covers_every_declared_table(self):
        """The setup must really write encrypted data into EVERY table in the map.

        This guard started with a numeric threshold ("at least 10 columns") and
        DID NOT WORK: 11 columns were found and it passed while
        `recurring_payments` had never been written, because the interceptor
        returned None silently without an `is_credit_card` flag. The threshold
        was not measuring coverage.

        The coverage is now bound to the map itself: if a write path silently
        stops working, the real test would scan that table empty and pass, so
        it is caught here.
        """
        from services.backup_service import ENCRYPTED_FIELDS

        self._exercise_every_encrypting_write_path()
        covered = {table for table, _ in self._columns_holding_encrypted_data()}
        missing = set(ENCRYPTED_FIELDS) - covered
        self.assertEqual(
            missing, set(),
            "Bu tablolara hiç şifreli veri yazılmadı; asıl test onları boş "
            f"tarayıp geçerdi: {sorted(missing)}",
        )

    def test_every_encrypted_column_on_disk_is_declared(self):
        """Every column carrying encrypted data on disk must be in ENCRYPTED_FIELDS.

        If it is not: that column does not enter the backup, is not migrated
        from the old format, and does not appear in the key verification -- all
        three silently.
        """
        from services.backup_service import ENCRYPTED_FIELDS

        self._exercise_every_encrypting_write_path()

        declared = {
            (table, field)
            for table, fields in ENCRYPTED_FIELDS.items()
            for field in fields
        }
        undeclared = self._columns_holding_encrypted_data() - declared

        self.assertEqual(
            undeclared, set(),
            "Bu sütunlar diskte şifreli veri tutuyor ama ENCRYPTED_FIELDS'te "
            "yok — yedeklemeden, migration'dan ve anahtar doğrulamasından "
            f"sessizce düşerler: {sorted(undeclared)}",
        )

    def test_declared_columns_exist_in_the_real_schema(self):
        """Every column in the map must really exist in the schema.

        The reverse direction: if a renamed or removed column stays in the map,
        the backup skips it silently (`if field in columns`) and the map stops
        reflecting reality.
        """
        from services.backup_service import ENCRYPTED_FIELDS


        self._exercise_every_encrypting_write_path()

        with closing(sqlite3.connect(self.db_path)) as conn:
            tables = {
                row[0] for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table, fields in ENCRYPTED_FIELDS.items():
                self.assertIn(
                    table, tables, f"{table} haritada var ama şemada yok"
                )
                columns = {
                    row[1] for row in conn.execute(f"PRAGMA table_info({table})")
                }
                missing = [f for f in fields if f not in columns]
                self.assertEqual(
                    missing, [],
                    f"{table}: haritadaki sütun(lar) şemada yok: {missing}",
                )


if __name__ == "__main__":
    unittest.main()
