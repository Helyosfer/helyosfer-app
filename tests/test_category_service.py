"""Adding categories and marking them essential or extra."""

import os
import tempfile
import unittest
from unittest import mock


class CategoryServiceTest(unittest.TestCase):
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

    def _category(self, name):
        from services.queries import list_categories

        return next((c for c in list_categories() if c["category"] == name), None)

    def test_the_defaults_are_listed_with_their_type_and_importance(self):
        salary = self._category("Maaş")
        self.assertEqual((salary["type"], salary["importance"]), ("income", "main"))
        takeaway = self._category("Paket Servis")
        self.assertEqual((takeaway["type"], takeaway["importance"]), ("expense", "extra"))

    def test_a_new_category_is_stored_trimmed_and_usable(self):
        from services.queries import CategoryService, add_category

        self.assertEqual(add_category("  Evcil   bakıcı ", "expense", True), "Evcil bakıcı")
        added = self._category("Evcil bakıcı")
        self.assertEqual((added["type"], added["importance"]), ("expense", "main"))
        names = [row[1] for row in CategoryService.get_categories("expense")]
        self.assertIn("Evcil bakıcı", names)

    def test_names_are_unique_whatever_the_case_including_turkish_letters(self):
        from services.queries import add_category

        add_category("Isıtma", "expense")
        for duplicate in ("ısıtma", "ISITMA", "maaş", "MAAŞ"):
            with self.subTest(duplicate=duplicate):
                with self.assertRaises(ValueError):
                    add_category(duplicate, "expense")

    def test_invalid_categories_are_refused(self):
        from services.queries import add_category

        for name, kind in (("", "expense"), ("   ", "income"), ("x" * 41, "expense"),
                           ("Yeni", "transfer")):
            with self.subTest(name=name, kind=kind):
                with self.assertRaises(ValueError):
                    add_category(name, kind)

    # -- renaming and removing ---------------------------------------------
    def _file_under(self, category):
        from services.account_service import AccountService
        from services.transaction_service import TransactionService

        account = AccountService.create_account("Main", "checking", 1000.0)
        TransactionService.add_transaction(
            account, 50.0, "expense", category, "x", detect_subscription=False)
        return account

    def test_a_built_in_category_can_be_renamed_and_becomes_the_users_own(self):
        from services.queries import rename_category

        self._file_under("Taksi")
        self.assertEqual(rename_category("Taksi", "Yolculuk"), "Yolculuk")
        self.assertIsNone(self._category("Taksi"))
        renamed = self._category("Yolculuk")
        self.assertTrue(renamed["custom"])
        self.assertTrue(renamed["in_use"])
        # It does not come back when the application starts again.
        from database.init_db import initialize_database

        initialize_database()
        self.assertIsNone(self._category("Taksi"))

    def test_a_built_in_category_can_be_removed_with_its_records_moved(self):
        from services.queries import delete_category

        self.assertTrue(delete_category("Otopark/Köprü"))
        self.assertIsNone(self._category("Otopark/Köprü"))
        self._file_under("Taksi")
        with self.assertRaises(ValueError):
            delete_category("Taksi")
        self.assertTrue(delete_category("Taksi", move_to="Toplu Taşıma"))
        self.assertIsNone(self._category("Taksi"))
        self.assertTrue(self._category("Toplu Taşıma")["in_use"])

    def test_categories_the_application_depends_on_cannot_be_changed(self):
        from services.queries import delete_category, protected_categories, rename_category

        self.assertEqual(
            set(protected_categories()),
            {"Varlık Alımı", "Varlık Satışı", "Kredi Taksiti", "Borç Ödeme", "Dijital Abonelik"},
        )
        for name in protected_categories():
            with self.subTest(name=name):
                self.assertTrue(self._category(name)["protected"])
                with self.assertRaises(ValueError):
                    rename_category(name, "Another name")
                with self.assertRaises(ValueError):
                    delete_category(name, move_to="Taksi")
                self.assertIsNotNone(self._category(name))
        self.assertFalse(self._category("Taksi")["protected"])

    def test_the_last_category_of_a_kind_cannot_be_removed(self):
        from services.queries import delete_category, list_categories, protected_categories

        income = [
            row["category"] for row in list_categories()
            if row["type"] == "income" and row["category"] not in protected_categories()
        ]
        for name in income[:-1]:
            delete_category(name)
        with self.assertRaises(ValueError):
            delete_category(income[-1])
        self.assertIsNotNone(self._category(income[-1]))

    def test_only_added_categories_are_marked_as_the_users_own(self):
        from services.queries import add_category

        add_category("Evcil bakıcı", "expense")
        self.assertTrue(self._category("Evcil bakıcı")["custom"])
        self.assertFalse(self._category("Maaş")["custom"])

    def test_renaming_moves_everything_filed_under_the_category(self):
        from database.db import get_connection
        from services.queries import add_category, rename_category

        add_category("Evcil bakıcı", "expense", True)
        self._file_under("Evcil bakıcı")
        conn = get_connection()
        try:
            conn.execute(
                "INSERT INTO monthly_budget_plan(type, name, amount, target_month,"
                " target_year, category_name) VALUES('expense', 'Bakım', 300, 1, 2026, ?)",
                ("Evcil bakıcı",))
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(rename_category("Evcil bakıcı", "  Köpek   gezdirme "), "Köpek gezdirme")
        self.assertIsNone(self._category("Evcil bakıcı"))
        renamed = self._category("Köpek gezdirme")
        self.assertEqual((renamed["type"], renamed["importance"], renamed["custom"]),
                         ("expense", "main", True))
        conn = get_connection()
        try:
            filed = conn.execute("SELECT category FROM transactions").fetchall()
            planned = conn.execute("SELECT category_name FROM monthly_budget_plan").fetchall()
        finally:
            conn.close()
        self.assertEqual([row[0] for row in filed], ["Köpek gezdirme"])
        self.assertEqual([row[0] for row in planned], ["Köpek gezdirme"])

    def test_a_rename_may_change_only_the_letter_case(self):
        from services.queries import add_category, rename_category

        add_category("evcil bakıcı", "expense")
        self.assertEqual(rename_category("evcil bakıcı", "Evcil Bakıcı"), "Evcil Bakıcı")

    def test_bad_renames_are_refused(self):
        from services.queries import add_category, rename_category

        add_category("Evcil bakıcı", "expense")
        for old, new in (("Evcil bakıcı", ""), ("Evcil bakıcı", "x" * 41),
                         ("Evcil bakıcı", "MAAŞ"), ("Borç Ödeme", "Ücret"), ("Yok", "Var")):
            with self.subTest(old=old, new=new):
                with self.assertRaises(ValueError):
                    rename_category(old, new)
        self.assertIsNotNone(self._category("Evcil bakıcı"))
        self.assertIsNotNone(self._category("Maaş"))

    def test_an_unused_category_of_the_users_can_be_removed(self):
        from services.queries import add_category, delete_category

        add_category("Evcil bakıcı", "expense")
        self.assertTrue(delete_category("Evcil bakıcı"))
        self.assertIsNone(self._category("Evcil bakıcı"))

    def test_a_category_in_use_or_protected_stays(self):
        from services.queries import add_category, delete_category

        add_category("Evcil bakıcı", "expense")
        self._file_under("Evcil bakıcı")
        for name in ("Evcil bakıcı", "Kredi Taksiti", "Yok"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    delete_category(name)
        self.assertIsNotNone(self._category("Evcil bakıcı"))

    def test_the_list_says_which_categories_are_in_use(self):
        from services.queries import add_category

        add_category("Evcil bakıcı", "expense")
        self.assertFalse(self._category("Evcil bakıcı")["in_use"])
        self._file_under("Evcil bakıcı")
        self.assertTrue(self._category("Evcil bakıcı")["in_use"])
        self.assertFalse(self._category("Maaş")["in_use"])

    def test_a_category_in_use_goes_when_its_records_are_moved(self):
        from database.db import get_connection
        from services.queries import add_category, delete_category

        add_category("Evcil bakıcı", "expense")
        self._file_under("Evcil bakıcı")
        self.assertTrue(delete_category("Evcil bakıcı", move_to="Taksi"))
        self.assertIsNone(self._category("Evcil bakıcı"))
        conn = get_connection()
        try:
            filed = [row[0] for row in conn.execute("SELECT category FROM transactions")]
        finally:
            conn.close()
        self.assertEqual(filed, ["Taksi"])

    def test_records_only_move_to_a_real_category_of_the_same_kind(self):
        from services.queries import add_category, delete_category

        add_category("Evcil bakıcı", "expense")
        self._file_under("Evcil bakıcı")
        for target in ("Maaş", "Yok Böyle", "Evcil bakıcı", "Kredi Taksiti"):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    delete_category("Evcil bakıcı", move_to=target)
        self.assertTrue(self._category("Evcil bakıcı")["in_use"])

    def test_changing_importance_ages_the_derived_figures(self):
        from services.asset_service import get_financial_data_revision
        from services.queries import set_category_importance

        before = get_financial_data_revision()
        self.assertTrue(set_category_importance("Paket Servis", True))
        self.assertEqual(self._category("Paket Servis")["importance"], "main")
        self.assertGreater(get_financial_data_revision(), before)
        self.assertTrue(set_category_importance("Paket Servis", False))
        self.assertEqual(self._category("Paket Servis")["importance"], "extra")

    def test_an_unknown_category_changes_nothing(self):
        from services.asset_service import get_financial_data_revision
        from services.queries import set_category_importance

        before = get_financial_data_revision()
        self.assertFalse(set_category_importance("Yok Böyle Bir Şey", True))
        self.assertEqual(get_financial_data_revision(), before)


if __name__ == "__main__":
    unittest.main()
