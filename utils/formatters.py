"""Masking and parsing for amount text the user types.

WHY A SEPARATE MODULE: live thousands-separator masking turns the input text
into `"250.000"`. Handing that text to `float()` produces **250.0** -- that
is, 250 thousand lira silently becomes 250 lira. Because money is involved,
this class of error has to be solved in one place, with tests.

THE AMBIGUITY AND HOW IT IS RESOLVED
------------------------------------
On its own `"250.000"` can be two things: Turkish grouping (250 thousand) or
English decimal (250.0). The module resolves this in two layers:

1. A masked input field keeps the CANONICAL numeric value alongside the
   visible text (`canonical_amount_text`); the save path reads that and never
   guesses. No ambiguity remains on masked fields.
2. For hand-written or legacy text, `parse_amount` looks for a strict
   grouping pattern (exact three-digit blocks after the first group, as in
   `1.234.567`); if the pattern holds it treats the separators as grouping,
   otherwise it falls back to the "the last separator is the decimal one"
   heuristic.

NOTE: parsing of exchange/currency API prices is DELIBERATELY kept
separate. That code reads machine text from exchange/currency APIs
("1,500,000.0000"); there, `"250.000"` really can mean 250.0. The two
contexts have different rules, so they were not merged.

"""

import re


DECIMAL_SEPARATOR = ","
GROUP_SEPARATOR = "."


MAX_DECIMALS = 2


_GROUPED_PATTERN = re.compile(r"^\d{1,3}(?:\.\d{3})+$")


MAX_INTEGER_DIGITS = 12


def _digits_and_decimal(text):
    """Turns text into (integer_digit_string, decimal_digit_string | None)."""
    raw = str(text or "")


    if DECIMAL_SEPARATOR in raw:
        integer_part, _, decimal_part = raw.partition(DECIMAL_SEPARATOR)
        return (
            re.sub(r"\D", "", integer_part),
            re.sub(r"\D", "", decimal_part)[:MAX_DECIMALS],
        )
    return re.sub(r"\D", "", raw), None


def parse_amount(text):
    """Converts user amount text to a float; raises ValueError if unreadable.

    Accepted formats:
      "1.500,50"   -> 1500.5   (Turkish: dot grouping, comma decimal)
      "15,000.00"  -> 15000.0  (English: comma grouping, dot decimal)
      "250.000"    -> 250000.0 (strict grouping pattern: three-digit blocks)
      "250.5"      -> 250.5    (does not match the grouping pattern -> decimal)
      "1500"       -> 1500.0
    """
    raw = str(text or "").strip()
    if not raw:
        raise ValueError("Tutar boş olamaz.")


    if "-" in raw:
        raise ValueError("Tutar negatif olamaz.")
    cleaned = raw.replace("₺", "").replace(" ", "").replace("+", "").strip()
    if not cleaned:
        raise ValueError("Tutar boş olamaz.")
    if not re.fullmatch(r"[\d.,]+", cleaned):
        raise ValueError(f"Geçersiz tutar: {text!r}")


    if _GROUPED_PATTERN.fullmatch(cleaned):
        return float(cleaned.replace(GROUP_SEPARATOR, ""))


    if _GROUPED_PATTERN.fullmatch(cleaned.replace(",", ".")) and "." not in cleaned:
        return float(cleaned.replace(",", ""))


    last_dot = cleaned.rfind(".")
    last_comma = cleaned.rfind(",")
    if last_dot > last_comma:
        normalized = cleaned.replace(",", "")
    elif last_comma > last_dot:
        normalized = cleaned.replace(".", "").replace(",", ".")
    else:
        normalized = cleaned

    try:
        return float(normalized)
    except ValueError:
        raise ValueError(f"Geçersiz tutar: {text!r}") from None


def parse_amount_to_float(text, default=0.0):
    """The never-raising variant of `parse_amount`.

    Not used on the save path (there the user has to be told "Invalid
    amount"); this is for places such as previews and live calculations where
    a value must always be present.
    """
    try:
        return parse_amount(text)
    except (ValueError, TypeError):
        return default


def format_amount_input(text):
    """Masks input text live: "250000" -> "250.000".

    To avoid disrupting typing order the decimal part is preserved AS IS:
    when the user types "1500," the comma is not removed (otherwise they
    could never start typing the kurus), and "1500,5" is not completed to
    "1.500,50".
    """
    integer_digits, decimal_digits = _digits_and_decimal(text)


    integer_digits = integer_digits.lstrip("0") or ("0" if integer_digits else "")

    grouped = ""
    if integer_digits:
        grouped = f"{int(integer_digits):,}".replace(",", GROUP_SEPARATOR)

    if decimal_digits is None:
        return grouped

    return f"{grouped or '0'}{DECIMAL_SEPARATOR}{decimal_digits}"


def format_amount_value(value):
    """Converts a numeric value into text writable to a masked field.

    1500.5 -> "1.500,50",  250000 -> "250.000,00"

    REQUIRED for programmatic assignments: writing `field.text = f"{1500.0:.2f}"`
    puts `"1500.00"` in the field; because the mask sees no decimal separator
    (comma) there, it counts every digit as an integer and produces
    `"150.000"` -- the value grows a hundredfold. This function supplies the
    decimal with a comma, so the mask preserves it.
    """
    number = float(value or 0)
    if number < 0:
        raise ValueError("Tutar negatif olamaz.")
    formatted = f"{number:,.{MAX_DECIMALS}f}"

    return formatted.replace(",", "X").replace(".", DECIMAL_SEPARATOR).replace(
        "X", GROUP_SEPARATOR)


def canonical_amount_text(text):
    """The canonical, parse-ready form of masked text ("1500.5")."""
    integer_digits, decimal_digits = _digits_and_decimal(text)
    if not integer_digits and not decimal_digits:
        return ""
    base = integer_digits.lstrip("0") or "0"
    if decimal_digits:
        return f"{base}.{decimal_digits}"
    return base


def filter_amount_keystroke(substring, existing_text=""):
    """Input filter for amount fields: digits and a SINGLE decimal separator only.

    Letters, signs and other symbols are dropped immediately. If the user
    types '.' out of English habit, that counts as DECIMAL intent and is
    converted to ',' -- otherwise it could not be told apart from the
    grouping dots the mask produces, and "1500.5" would silently become
    15005.
    """
    text = str(substring or "")
    current = str(existing_text or "")
    already_has_decimal = DECIMAL_SEPARATOR in current


    integer_part = current.split(DECIMAL_SEPARATOR)[0]
    integer_digits = sum(1 for char in integer_part if char.isdigit())

    result = []
    for char in text:
        if char.isdigit():
            if not already_has_decimal and integer_digits >= MAX_INTEGER_DIGITS:
                continue
            if not already_has_decimal:
                integer_digits += 1
            result.append(char)
        elif char in (DECIMAL_SEPARATOR, GROUP_SEPARATOR):
            if not already_has_decimal:
                result.append(DECIMAL_SEPARATOR)
                already_has_decimal = True

    return "".join(result)


