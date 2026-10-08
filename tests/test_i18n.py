import unittest

from ui.i18n import get_language, set_language, tr


class I18nTestCase(unittest.TestCase):
    def tearDown(self):
        set_language("en")

    def test_language_fallback_and_switch(self):
        self.assertEqual(set_language("en"), "en")
        self.assertEqual(tr("Ayarlar"), "Settings")
        self.assertEqual(tr("Bilinmeyen metin"), "Bilinmeyen metin")
        self.assertEqual(set_language("unsupported"), "en")
        self.assertEqual(get_language(), "en")

    def test_dynamic_ui_sentences_are_translated(self):
        """Dynamic sentences are now built FROM A TEMPLATE.

        This test used to say `tr("Taksit Sayısı: 6")` and relied on the
        substring-replacing fallback. That fallback translated user data too
        (see tests/test_i18n_user_data.py) and was removed. The contract now:
        the template is translated and the number is substituted
        afterwards.
        """
        from ui.i18n import trf

        set_language("en")
        self.assertEqual(
            trf("Taksit Sayısı: {count}", count=6),
            "Number of Instalments: 6",
        )
        self.assertEqual(
            trf("Aylık: {monthly_payment} ₺", monthly_payment="1.250"),
            "Monthly: 1.250 ₺",
        )
        self.assertEqual(tr("Maaş"), "Salary")

    def test_retired_locale_codes_fall_back_to_english(self):
        set_language("tr")
        self.assertEqual(tr("What-If\nSandbox"), "What-If\nSandbox")
        self.assertEqual(tr("What-If Sandbox"), "What-If Sandbox")


    def test_account_dashboard_dynamic_phrases_are_translated(self):
        from ui.i18n import trf

        set_language("en")
        # Static labels remain as complete keys.
        self.assertEqual(tr("Değişim (Bugün)"), "Change (Today)")
        self.assertEqual(tr("Nakit / Vadesiz"), "Cash / Checking")

        self.assertEqual(
            trf("{count} TL dışı varlık • Canlı değer", count=3),
            "3 non-TRY assets • Live value",
        )




if __name__ == "__main__":
    unittest.main()
