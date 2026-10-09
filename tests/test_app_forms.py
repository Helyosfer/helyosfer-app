"""Form input handling shared by the account and transaction dialogs."""

import datetime
import unittest

try:
    from app.accounts import FormError, read_amount, read_date, user_message
    from app.assets import format_quantity, read_quantity
    from app.controllers import display_title, mask_amount, short_date
    from app.insight import read_percent, read_signed_amount
    from app.payments import due_phrase, read_count
except ImportError:  # pragma: no cover - the interface toolkit is optional for core tests
    read_amount = None


@unittest.skipIf(read_amount is None, "PySide6 is not installed")
class FormInputTest(unittest.TestCase):
    def test_turkish_grouping_is_read_as_thousands(self):
        self.assertEqual(read_amount("1.250,50", "amount"), 1250.50)
        self.assertEqual(read_amount("250.000", "amount"), 250000.0)

    def test_thousands_are_grouped_as_an_amount_is_typed(self):
        typed = [mask_amount("1234567"[:n]) for n in range(1, 8)]
        self.assertEqual(
            typed, ["1", "12", "123", "1.234", "12.345", "123.456", "1.234.567"]
        )
        self.assertEqual(mask_amount("1.2345"), "12.345")
        self.assertEqual(mask_amount("1000,"), "1.000,")
        self.assertEqual(mask_amount("1000,5"), "1.000,5")
        self.assertEqual(mask_amount("abc1000tl"), "1.000")
        self.assertEqual(mask_amount(""), "")

    def test_what_the_mask_shows_is_what_gets_saved(self):
        for typed, value in (("1000", 1000.0), ("1250,5", 1250.5), ("250000", 250000.0),
                             ("999", 999.0), ("0,75", 0.75)):
            with self.subTest(typed=typed):
                self.assertEqual(read_amount(mask_amount(typed), "amount"), value)

    def test_a_minus_survives_only_where_one_is_allowed(self):
        self.assertEqual(mask_amount("-2500", signed=True), "-2.500")
        self.assertEqual(mask_amount("-", signed=True), "-")
        self.assertEqual(mask_amount("−2500", signed=True), "-2.500")
        self.assertEqual(mask_amount("-2500"), "2.500")
        self.assertEqual(read_signed_amount(mask_amount("-2500", signed=True)), -2500.0)

    def test_an_empty_required_amount_is_refused(self):
        with self.assertRaises(FormError):
            read_amount("  ", "amount")

    def test_an_empty_optional_amount_is_zero(self):
        self.assertEqual(read_amount("", "balance", optional=True), 0.0)

    def test_garbage_is_refused_without_echoing_the_input(self):
        with self.assertRaises(FormError) as caught:
            read_amount("abc<script>", "amount")
        self.assertNotIn("abc", str(caught.exception))

    def test_an_empty_date_and_today_both_mean_now(self):
        today = datetime.date.today().strftime("%d.%m.%Y")
        self.assertIsNone(read_date(""))
        self.assertIsNone(read_date(today))

    def test_another_day_becomes_a_full_timestamp(self):
        stamp = read_date("05.03.2026")
        self.assertTrue(stamp.startswith("2026-03-05 "))
        self.assertEqual(len(stamp), 19)

    def test_an_impossible_date_is_refused(self):
        with self.assertRaises(FormError):
            read_date("31.02.2026")
        with self.assertRaises(FormError):
            read_date("2026-03-05")

    def test_a_catalogued_service_refusal_is_shown_in_english(self):
        message = user_message(ValueError("Hesap adı boş olamaz."))
        self.assertNotEqual(message, "Hesap adı boş olamaz.")
        self.assertTrue(message)

    def test_an_uncatalogued_refusal_never_reaches_the_user_raw(self):
        message = user_message(ValueError("Geçersiz tutar: 'gizli-veri'"))
        self.assertNotIn("gizli-veri", message)

    def test_generated_debt_payment_titles_are_shown_in_english(self):
        self.assertEqual(
            display_title("Travel card Borç Ödemesi"), "Travel card debt payment"
        )
        self.assertEqual(display_title("Weekly shop"), "Weekly shop")

    def test_other_generated_descriptions_are_reworded_and_keep_the_name(self):
        cases = {
            "Netflix (Otomatik)": "Netflix (automatic)",
            "Telefon (2 Taksit Ödemesi)": "Telefon (2 installments)",
            "Telefon (1 Taksit Ödemesi)": "Telefon (1 installment)",
            "Araba (Tamamen Kapatma)": "Araba (paid off)",
            "Araba (Otomatik Taksit Ödemesi)": "Araba (automatic installment)",
            "THY (THYAO) alındı — 100 adet, birim fiyat 280,40 ₺": "Bought 100 × THY (THYAO)",
            "THY (THYAO) satıldı — 40.0 adet, birim fiyat 312,50 ₺": "Sold 40 × THY (THYAO)",
            "Gram Altın (GC=F) alındı — 12.5 adet, birim fiyat 5.400,00 ₺":
                "Bought 12,5 × Gram gold (GC=F)",
        }
        for stored, shown in cases.items():
            with self.subTest(stored=stored):
                self.assertEqual(display_title(stored), shown)

    def test_quantities_accept_small_fractions_and_turkish_separators(self):
        self.assertEqual(read_quantity("0,015"), 0.015)
        self.assertEqual(read_quantity("0.00012"), 0.00012)
        self.assertEqual(read_quantity("1.250,5"), 1250.5)
        for bad in ("", "abc", "0", "-3"):
            with self.subTest(bad=bad):
                with self.assertRaises(FormError):
                    read_quantity(bad)

    def test_quantities_are_shown_without_trailing_zeros(self):
        self.assertEqual(format_quantity(100.0), "100")
        self.assertEqual(format_quantity(12.5), "12,5")
        self.assertEqual(format_quantity(0.015), "0,015")
        self.assertEqual(format_quantity(1250.5), "1.250,5")

    def test_dates_in_either_stored_format_are_shortened(self):
        self.assertEqual(short_date("2026-10-08 10:00:00"), "08 Oct")
        self.assertEqual(short_date("08/10/2026"), "08 Oct")
        self.assertEqual(short_date("not a date"), "not a date")

    def test_percentages_accept_signs_commas_and_blank(self):
        self.assertEqual(read_percent("", "change"), 0.0)
        self.assertEqual(read_percent("-5", "change"), -5.0)
        self.assertEqual(read_percent("12,5 %", "change"), 12.5)
        for bad in ("abc", "-150", "5000"):
            with self.subTest(bad=bad):
                with self.assertRaises(FormError):
                    read_percent(bad, "change")

    def test_one_time_amounts_keep_their_sign(self):
        self.assertEqual(read_signed_amount(""), 0.0)
        self.assertEqual(read_signed_amount("5.000"), 5000.0)
        self.assertEqual(read_signed_amount("-2.500,50"), -2500.5)
        with self.assertRaises(FormError):
            read_signed_amount("lots")

    def test_counts_are_whole_numbers_within_their_range(self):
        self.assertEqual(read_count(" 12 ", "months", 1, 360), 12)
        for bad in ("", "1,5", "0", "361"):
            with self.subTest(bad=bad):
                with self.assertRaises(FormError):
                    read_count(bad, "months", 1, 360)

    def test_due_dates_are_described_relative_to_today(self):
        import datetime

        today = datetime.date(2026, 10, 8)
        self.assertEqual(due_phrase("2026-10-08", today), ("08 Oct  ·  today", False))
        self.assertEqual(due_phrase("2026-10-09", today), ("09 Oct  ·  tomorrow", False))
        self.assertEqual(due_phrase("2026-10-20", today), ("20 Oct  ·  in 12 days", False))
        self.assertEqual(due_phrase("2026-10-06", today), ("06 Oct  ·  2 days overdue", True))


if __name__ == "__main__":
    unittest.main()
