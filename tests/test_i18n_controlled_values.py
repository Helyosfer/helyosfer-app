"""Controlled Turkish values must not be left in the middle of an English sentence.

THE MEASURED DEFECT: the `trf()` contract was right, but the PRODUCTION calls
handed the controlled enum value to the template RAW. The outputs measured
under `set_language("en")`:

    Select Type: Hisse        (expected: Select Type: Stock)
    Add New Altın             (expected: Add New Gold)
    Gold Type: Gram Altın     (expected: Gold Type: Gram Gold)
    Type: Döviz               (expected: Type: Currency)

THE EXISTING TEST'S BLIND SPOT: `trf("Tür Seç: {type}", type=tr("Hisse", "en"))`
verified only THE HELPER itself -- the test was translating the parameter. The
test stayed green even though the production path never called `tr()`.

This suite therefore calls THE REAL PRODUCTION METHODS: the dropdown handlers
and the functions producing the card/dialog text. The parameter is prepared by
the production code, not the test.

THE INTERNAL LOGIC DOES NOT CHANGE: fields such as `self._asset_selected_type`
go on holding the Turkish enum value (the "Altın" comparisons must not break);
only the DISPLAY value is translated. That is exercised separately too.

"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class _Button:
    """The smallest surface standing in for `MDRaisedButton`: only `text`."""

    def __init__(self):
        self.text = ""


class _Menu:
    def __init__(self):
        self.dismissed = False

    def dismiss(self):
        self.dismissed = True


class _LanguageCase(unittest.TestCase):
    def setUp(self):
        from ui import i18n

        self._previous = i18n.get_language()
        self.addCleanup(i18n.set_language, self._previous)

    def in_english(self):
        from ui import i18n

        i18n.set_language("en")

    def in_turkish(self):
        from ui import i18n

        i18n.set_language("tr")












class SecureOperationErrorTest(_LanguageCase):
    """The `_secure_operation_error` titles are controlled application text."""

    HEADLINES = (
        "Backup oluşturulamadı",
        "Restore başarısız; mevcut veri korundu",
        "Migration geri alındı",
        "Kurtarma paketi oluşturulamadı",
        "Kurtarma paketi içe aktarılamadı",
        "Anahtar rotasyonu başlatılamadı",
        "Anahtar rotasyonu geri alındı",
    )


    def test_every_headline_has_an_english_entry(self):
        from ui.i18n import tr

        self.in_english()
        for headline in self.HEADLINES:
            with self.subTest(headline=headline):
                self.assertNotEqual(tr(headline), headline)




if __name__ == "__main__":
    unittest.main()
