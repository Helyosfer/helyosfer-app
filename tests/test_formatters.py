"""Amount masking and parsing tests.

Money parsing is where silent errors are most expensive: masking turns the
input into `"250.000"`, and handing that to `float()` produces 250.0 -- that is,
250 thousand lira becomes 250 lira. This suite locks that class of error down.

"""
import os
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import formatters
from utils.formatters import (
    canonical_amount_text,
    filter_amount_keystroke,
    format_amount_input,
    format_amount_value,
    parse_amount,
    parse_amount_to_float,
)


class ParseAmountTest(unittest.TestCase):
    """Item (a) of the task description and its near neighbours."""

    def test_turkish_format(self):
        self.assertAlmostEqual(parse_amount("1.500,50"), 1500.50, places=2)

    def test_english_format(self):
        self.assertAlmostEqual(parse_amount("15,000.00"), 15000.00, places=2)

    def test_garbage_raises(self):
        for bad in ("abc", "12abc", "₺₺", "--"):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    parse_amount(bad)

    def test_garbage_returns_default_in_safe_variant(self):
        for bad in ("abc", "", None, "12abc"):
            with self.subTest(value=bad):
                self.assertEqual(parse_amount_to_float(bad), 0.0)

    def test_safe_variant_honours_custom_default(self):
        self.assertEqual(parse_amount_to_float("abc", default=-1.0), -1.0)

    def test_grouped_text_is_not_read_as_decimal(self):
        """The text the mask produces must be read correctly -- the critical case.

        float("250.000") gives 250.0; 250000.0 is expected here.
        """
        self.assertAlmostEqual(parse_amount("250.000"), 250000.0, places=2)
        self.assertAlmostEqual(parse_amount("1.500"), 1500.0, places=2)
        self.assertAlmostEqual(parse_amount("1.234.567"), 1234567.0, places=2)

    def test_non_grouped_dot_is_decimal(self):
        """A dot that does NOT match the three-digit grouping pattern is a decimal."""
        self.assertAlmostEqual(parse_amount("250.5"), 250.5, places=2)
        self.assertAlmostEqual(parse_amount("250.55"), 250.55, places=2)

    def test_plain_integer_and_decimal(self):
        self.assertAlmostEqual(parse_amount("1500"), 1500.0, places=2)
        self.assertAlmostEqual(parse_amount("0,99"), 0.99, places=2)

    def test_currency_symbol_and_spaces_tolerated(self):
        self.assertAlmostEqual(parse_amount(" ₺1.500,50 "), 1500.50, places=2)

    def test_negative_is_rejected(self):
        """The direction is set by the Income/Expense selection; a negative amount is not accepted."""
        with self.assertRaises(ValueError):
            parse_amount("-500")

    def test_empty_is_rejected(self):
        for blank in ("", "   ", None):
            with self.subTest(value=blank):
                with self.assertRaises(ValueError):
                    parse_amount(blank)


class LiveMaskTest(unittest.TestCase):
    """Live formatting (SECTION 1)."""

    def test_thousands_separator_inserted(self):
        self.assertEqual(format_amount_input("250000"), "250.000")
        self.assertEqual(format_amount_input("1500"), "1.500")
        self.assertEqual(format_amount_input("1234567"), "1.234.567")

    def test_short_numbers_untouched(self):
        for value in ("1", "15", "150"):
            with self.subTest(value=value):
                self.assertEqual(format_amount_input(value), value)

    def test_decimal_separator_is_preserved_while_typing(self):
        """While typing '1500,' the comma must not be deleted, or the kurus cannot be written."""
        self.assertEqual(format_amount_input("1500,"), "1.500,")
        self.assertEqual(format_amount_input("1500,5"), "1.500,5")
        self.assertEqual(format_amount_input("1500,50"), "1.500,50")

    def test_decimals_clamped_to_two(self):
        self.assertEqual(format_amount_input("15,9999"), "15,99")

    def test_leading_zeros_collapsed(self):
        self.assertEqual(format_amount_input("000123"), "123")
        self.assertEqual(format_amount_input("0"), "0")

    def test_bare_decimal_gets_zero_prefix(self):
        self.assertEqual(format_amount_input(",5"), "0,5")

    def test_empty_stays_empty(self):
        self.assertEqual(format_amount_input(""), "")

    def test_mask_is_idempotent(self):
        """Re-masking already-masked text must not corrupt the value."""
        for value in ("250000", "1500,5", "1234567", "0,99"):
            once = format_amount_input(value)
            with self.subTest(value=value):
                self.assertEqual(format_amount_input(once), once)


class CanonicalValueTest(unittest.TestCase):
    """The canonical (parse-ready) form of masked text."""

    def test_canonical_strips_grouping(self):
        self.assertEqual(canonical_amount_text("250.000"), "250000")
        self.assertEqual(canonical_amount_text("1.500,50"), "1500.50")

    def test_canonical_parses_back_to_same_number(self):
        for typed, expected in (
            ("250000", 250000.0),
            ("1500,5", 1500.5),
            ("1234567,89", 1234567.89),
            ("0,99", 0.99),
        ):
            with self.subTest(typed=typed):
                displayed = format_amount_input(typed)
                canonical = canonical_amount_text(displayed)
                self.assertAlmostEqual(float(canonical), expected, places=2)

    def test_canonical_of_empty_is_empty(self):
        self.assertEqual(canonical_amount_text(""), "")


class FormatAmountValueTest(unittest.TestCase):
    """The programmatic assignment path -- where the 100x error is prevented."""

    def test_value_formatted_with_turkish_separators(self):
        self.assertEqual(format_amount_value(1500.0), "1.500,00")
        self.assertEqual(format_amount_value(250000), "250.000,00")
        self.assertEqual(format_amount_value(149.99), "149,99")

    def test_round_trip_through_mask_is_stable(self):
        """Text written with format_amount_value must not change when passed through the mask."""
        for value in (1500.0, 1500.5, 250000, 149.99, 0, 1234567.89):
            with self.subTest(value=value):
                displayed = format_amount_value(value)
                self.assertEqual(format_amount_input(displayed), displayed)
                self.assertAlmostEqual(
                    parse_amount(displayed), float(value), places=2)

    def test_raw_float_string_would_have_been_misread(self):
        """Why format_amount_value is required: raw f"{v:.2f}" text inflates 100x in the mask.

        This test documents not the correct behaviour but the trap AVOIDED.
        """
        self.assertEqual(format_amount_input("1500.00"), "150.000")
        self.assertEqual(format_amount_value(1500.00), "1.500,00")

    def test_negative_value_rejected(self):
        with self.assertRaises(ValueError):
            format_amount_value(-5)


class KeystrokeFilterTest(unittest.TestCase):
    """Input restrictions (SECTION 1.2)."""

    def test_digits_pass(self):
        self.assertEqual(filter_amount_keystroke("7", "12"), "7")

    def test_letters_and_symbols_blocked(self):
        for bad in ("a", "Z", "!", " ", "€", "/"):
            with self.subTest(char=bad):
                self.assertEqual(filter_amount_keystroke(bad, "12"), "")

    def test_signs_blocked(self):
        for sign in ("-", "+"):
            with self.subTest(sign=sign):
                self.assertEqual(filter_amount_keystroke(sign, ""), "")

    def test_dot_becomes_decimal_comma(self):
        """A '.' typed out of English habit counts as decimal intent.

        Otherwise it cannot be told apart from the mask's grouping dots and
        "1500.5" would silently become 15005.
        """
        self.assertEqual(filter_amount_keystroke(".", "1500"), ",")

    def test_second_decimal_separator_blocked(self):
        for existing in ("1500,5", "1.500,"):
            for char in (",", "."):
                with self.subTest(existing=existing, char=char):
                    self.assertEqual(
                        filter_amount_keystroke(char, existing), "")

    def test_pasted_text_is_cleaned(self):
        """Only the valid characters survive from pasted mixed text."""
        self.assertEqual(filter_amount_keystroke("1a2b3", ""), "123")
        self.assertEqual(filter_amount_keystroke("12.50abc", ""), "12,50")

    def test_pasted_text_keeps_single_separator(self):
        self.assertEqual(filter_amount_keystroke("1.2.3", ""), "1,23")

    def test_pasted_negative_loses_only_its_sign(self):
        """Pasting "-500" leaves 500; the direction is set by the Income/Expense selection.

        Dropping the amount entirely would be silently destroying the number
        the user typed; dropping the sign preserves the magnitude and discards
        the direction, which is meaningless here. This behaviour is
        deliberate.
        """
        self.assertEqual(filter_amount_keystroke("-500", ""), "500")


if __name__ == "__main__":
    unittest.main()


class AmountUpperBoundTest(unittest.TestCase):
    """Absurd amounts must never get into the field at all.

    A user report: entering a very long number made the application "go mad" --
    totals such as ₺112,955,698,541,615,249,872,910.00 appeared on screen.
    float64 carries integers exactly only up to 2**53 (about 9.007e15); beyond
    that, balance arithmetic rounds silently. The bound is applied at INPUT
    time, so existing records are unaffected.
    """

    def test_integer_part_is_capped(self):
        limit = formatters.MAX_INTEGER_DIGITS
        full = "9" * limit
        self.assertEqual(
            filter_amount_keystroke("9", full), "",
            "Tam kısım sınıra ulaştığında yeni hane kabul edilmemeli.",
        )

    def test_below_the_cap_still_accepts_digits(self):
        almost = "9" * (formatters.MAX_INTEGER_DIGITS - 1)
        self.assertEqual(filter_amount_keystroke("9", almost), "9")

    def test_cap_stays_within_float64_exact_integer_range(self):
        biggest = 10 ** formatters.MAX_INTEGER_DIGITS - 1
        self.assertLess(
            biggest, 2 ** 53,
            "Sınır, float64'ün tam sayı kesinlik aralığının içinde kalmalı.",
        )

    def test_decimals_are_unaffected_by_the_integer_cap(self):
        """The bound applies only to the INTEGER part; writing the kurus must not be blocked."""
        capped = "9" * formatters.MAX_INTEGER_DIGITS + ",5"
        self.assertEqual(filter_amount_keystroke("0", capped), "0")
