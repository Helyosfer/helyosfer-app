"""Form input handling shared by the account and transaction dialogs."""

import datetime
import unittest

try:
    from app.accounts import FormError, read_amount, read_date, user_message
    from app.controllers import display_title
except ImportError:  # pragma: no cover - the interface toolkit is optional for core tests
    read_amount = None


@unittest.skipIf(read_amount is None, "PySide6 is not installed")
class FormInputTest(unittest.TestCase):
    def test_turkish_grouping_is_read_as_thousands(self):
        self.assertEqual(read_amount("1.250,50", "amount"), 1250.50)
        self.assertEqual(read_amount("250.000", "amount"), 250000.0)

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


if __name__ == "__main__":
    unittest.main()
