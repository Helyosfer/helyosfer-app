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
