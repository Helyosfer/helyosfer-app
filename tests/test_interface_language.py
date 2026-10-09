"""The Turkish interface is complete and the language switch works."""

import ast
import json
import re
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
QML_TEXT = re.compile(r'qsTr\(\s*"((?:[^"\\]|\\.)*)"\s*\)')
QML_DYNAMIC = re.compile(r"qsTr\(\s*[^\"\s)]")
FILLED_BY_QML = re.compile(r"%\d+")
FILLED_BY_PYTHON = re.compile(r"\{\d+\}")

try:
    from app import language
    from app.turkish import TEXT
except ImportError:  # pragma: no cover - the interface toolkit is optional for core tests
    language = None


def interface_text() -> dict[str, str]:
    """Every text the interface looks up, with the file it was found in."""
    found: dict[str, str] = {}
    for path in sorted((PROJECT_ROOT / "app" / "qml").rglob("*.qml")):
        for match in QML_TEXT.finditer(path.read_text(encoding="utf-8")):
            found.setdefault(json.loads(f'"{match.group(1)}"'), path.name)
    for path in sorted((PROJECT_ROOT / "app").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and getattr(node.func, "id", "") in ("say", "later")
                    and node.args and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                found.setdefault(node.args[0].value, path.name)
    return found


@unittest.skipIf(language is None, "PySide6 is not installed")
class TurkishTableTest(unittest.TestCase):
    def test_every_interface_text_has_a_turkish_entry(self):
        missing = {text: where for text, where in interface_text().items() if text not in TEXT}
        self.assertEqual(missing, {})

    def test_the_table_holds_nothing_the_interface_no_longer_says(self):
        self.assertEqual(sorted(set(TEXT) - set(interface_text())), [])

    def test_an_entry_keeps_the_placeholders_of_its_source(self):
        for source, turkish in TEXT.items():
            with self.subTest(source=source):
                self.assertEqual(
                    sorted(FILLED_BY_PYTHON.findall(source)),
                    sorted(FILLED_BY_PYTHON.findall(turkish)))
                # Turkish writes a percentage as "%5", which only looks like a
                # QML placeholder; it matters where the source has real ones.
                if FILLED_BY_QML.search(source):
                    self.assertEqual(
                        sorted(FILLED_BY_QML.findall(source)),
                        sorted(FILLED_BY_QML.findall(turkish)))

    def test_no_entry_is_empty_or_left_in_english(self):
        same = {"Net", "1Y", "today"} - {"today"}
        for source, turkish in TEXT.items():
            with self.subTest(source=source):
                self.assertTrue(turkish.strip())
                if source not in same:
                    self.assertNotEqual(source, turkish)

    def test_qml_never_looks_up_text_it_builds(self):
        """`qsTr(variable)` would look up a user's own text, or nothing at all."""
        for path in sorted((PROJECT_ROOT / "app" / "qml").rglob("*.qml")):
            with self.subTest(file=path.name):
                self.assertIsNone(QML_DYNAMIC.search(path.read_text(encoding="utf-8")))


@unittest.skipIf(language is None, "PySide6 is not installed")
class LanguageSwitchTest(unittest.TestCase):
    def tearDown(self):
        language.set_language(language.ENGLISH)

    def test_english_is_the_text_as_written(self):
        language.set_language("en")
        self.assertEqual(language.say("Choose an account."), "Choose an account.")
        self.assertEqual(language.say("in {0} days", 3), "in 3 days")

    def test_turkish_comes_from_the_table_with_values_filled_in_afterwards(self):
        language.set_language("tr")
        self.assertEqual(language.say("Choose an account."), "Bir hesap seçin.")
        self.assertEqual(language.say("in {0} days", 3), "3 gün sonra")
        self.assertEqual(language.say("{0} of {1} paid", 4, 12), "12 taksitin 4 tanesi ödendi")

    def test_a_value_is_never_looked_up_itself(self):
        language.set_language("tr")
        self.assertEqual(language.say("Saved {0}.", "Settings"), "Settings kaydedildi.")

    def test_unknown_text_is_shown_as_it_is(self):
        language.set_language("tr")
        self.assertEqual(language.say("My own account"), "My own account")

    def test_an_unknown_language_falls_back_to_english(self):
        self.assertEqual(language.set_language("de"), "en")

    def test_service_text_is_english_or_left_in_turkish(self):
        language.set_language("en")
        self.assertEqual(language.tr("Maaş"), "Salary")
        language.set_language("tr")
        self.assertEqual(language.tr("Maaş"), "Maaş")
        self.assertEqual(language.tr(None), "")

    def test_a_services_own_message_follows_the_interface(self):
        from ui.i18n import tr as service_text, trf

        language.set_language("tr")
        self.assertEqual(service_text("Hatalı Şifre!"), "Hatalı Şifre!")
        self.assertEqual(
            trf("Taksit Sayısı: {count}", count=6), "Taksit Sayısı: 6")
        # Asking for a catalog by name still gets that catalog.
        self.assertEqual(service_text("Hatalı Şifre!", "en"), "Incorrect password!")
        language.set_language("en")
        self.assertEqual(service_text("Hatalı Şifre!"), "Incorrect password!")
        self.assertEqual(
            trf("Taksit Sayısı: {count}", count=6), "Number of Instalments: 6")

    def test_a_percentage_is_written_the_way_each_language_writes_it(self):
        language.set_language("en")
        self.assertEqual(language.percent(27), "27 %")
        self.assertEqual(language.percent(5.94, 1, signed=True), "+5,9 %")
        self.assertEqual(language.percent(-19.2, 1, signed=True), "−19,2 %")
        language.set_language("tr")
        self.assertEqual(language.percent(27), "%27")
        self.assertEqual(language.percent(5.94, 1, signed=True), "+%5,9")
        self.assertEqual(language.percent(-19.2, 1, signed=True), "−%19,2")

    def test_a_trade_the_application_recorded_reads_cleanly_in_turkish(self):
        from app.controllers import display_title

        stored = "THYAO (THYAO) alındı — 10.0000 adet"
        language.set_language("tr")
        self.assertEqual(display_title(stored), "THYAO (THYAO) alındı — 10 adet")
        self.assertEqual(
            display_title("Gram Altın (GC=F) satıldı — 2.5000 adet"),
            "Gram Altın (GC=F) satıldı — 2,5 adet")
        language.set_language("en")
        self.assertEqual(display_title(stored), "Bought 10 × THYAO (THYAO)")

    def test_the_schedule_pdf_has_turkish_for_everything_it_prints(self):
        from services.loan_report import PRINTED_TEXT

        self.assertEqual([text for text in PRINTED_TEXT if text not in TEXT], [])

    def test_month_names_tell_may_from_its_abbreviation(self):
        language.set_language("tr")
        self.assertEqual((language.month_name(5), language.month_short(5)), ("Mayıs", "May"))
        self.assertEqual(language.month_short(10), "Eki")
        language.set_language("en")
        self.assertEqual((language.month_name(5), language.month_short(10)), ("May", "Oct"))

    def test_blanks_read_as_a_sentence_in_turkish(self):
        from app.accounts import FormError, read_amount

        language.set_language("tr")
        with self.assertRaises(FormError) as caught:
            read_amount("", language.say("amount"))
        self.assertEqual(str(caught.exception), "Lütfen tutar girin.")

    def test_a_service_refusal_is_shown_in_the_chosen_language(self):
        from app.accounts import user_message

        refusal = ValueError("Kategori adı boş olamaz.")
        language.set_language("en")
        self.assertEqual(user_message(refusal), "Enter a name for the category.")
        self.assertEqual(
            user_message(ValueError("something raw")),
            "This could not be saved. Check the values and try again.")
        language.set_language("tr")
        self.assertEqual(user_message(refusal), "Kategori adı boş olamaz.")
        self.assertEqual(
            user_message(ValueError("something raw")),
            "Kaydedilemedi. Değerleri kontrol edip yeniden deneyin.")

    def test_stored_descriptions_are_reworded_only_for_english(self):
        from app.controllers import display_title

        stored = "Seyahat kartı Borç Ödemesi"
        language.set_language("en")
        self.assertEqual(display_title(stored), "Seyahat kartı debt payment")
        language.set_language("tr")
        self.assertEqual(display_title(stored), stored)

    def test_the_computer_decides_until_a_language_is_chosen(self):
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {language.OVERRIDE_ENV: "tr"}):
            self.assertEqual(language.system_language(), "tr")
        with mock.patch.dict(os.environ, {language.OVERRIDE_ENV: "en"}):
            self.assertEqual(language.system_language(), "en")
        with mock.patch.dict(os.environ, {language.OVERRIDE_ENV: ""}), \
             mock.patch("locale.getlocale", return_value=("Turkish_Türkiye", "1254")):
            self.assertEqual(language.system_language(), "tr")
        with mock.patch.dict(os.environ, {language.OVERRIDE_ENV: ""}), \
             mock.patch("app.language._windows_shows_turkish", return_value=False), \
             mock.patch("locale.getlocale", return_value=("en_US", "UTF-8")):
            self.assertEqual(language.system_language(), "en")
        # Windows displayed in Turkish counts even when dates and numbers are
        # formatted the English way; the locale reports only the format.
        with mock.patch.dict(os.environ, {language.OVERRIDE_ENV: ""}), \
             mock.patch("app.language._windows_shows_turkish", return_value=True), \
             mock.patch("locale.getlocale", return_value=("English_United Kingdom", "1252")):
            self.assertEqual(language.system_language(), "tr")

    def test_the_display_language_of_windows_is_read_from_its_low_bits(self):
        import os
        from unittest import mock

        if os.name != "nt":
            self.assertFalse(language._windows_shows_turkish())
            return
        for identifier, expected in ((0x041F, True), (0x0409, False), (0x0809, False)):
            with self.subTest(identifier=hex(identifier)), mock.patch(
                "ctypes.windll.kernel32.GetUserDefaultUILanguage", return_value=identifier,
            ):
                self.assertEqual(language._windows_shows_turkish(), expected)


if __name__ == "__main__":
    unittest.main()
