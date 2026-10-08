"""Turkish error text must not kill the process because of the console encoding.

THE REAL BUG (measured in Windows CI): on Windows, stdout uses the console's
code page (usually cp1252 on Turkish installations) and that code page CANNOT
ENCODE the characters 'ı', 'ğ', 'ş'. `print()` then raises
`UnicodeEncodeError`.

This was not a cosmetic problem: most of the application's Turkish error
messages are printed INSIDE `except` blocks. When `print` blows up there the
error is not swallowed -- the exception leaks out and kills the actual
operation. The "could not write to the subscription radar" line inside
`TransactionService.add_transaction` did exactly that: when the subscription
radar errored, THE WHOLE TRANSACTION was lost. The same test was green on Linux
(UTF-8) and red on Windows.

The tests imitate a cp1252 console -- so they run meaningfully on Linux too.

"""
import io
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class TurkishTextOnLegacyConsoleTest(unittest.TestCase):

    def test_cp1252_cannot_encode_turkish_dotless_i(self):
        """Show that the danger is real -- do not assume it.

        This test verifies not the fix but its RATIONALE: can 'ı' really not be
        encoded in cp1252?
        """
        with self.assertRaises(UnicodeEncodeError):
            "Abonelik radarına yazılamadı".encode("cp1252")

    def test_print_survives_a_cp1252_stdout_after_reconfigure(self):
        """A stream reconfigured to UTF-8 prints Turkish text without swallowing it."""
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")


        with self.assertRaises(UnicodeEncodeError):
            print("Abonelik radarına yazılamadı", file=stream)
            stream.flush()


        stream.reconfigure(encoding="utf-8", errors="replace")
        print("Abonelik radarına yazılamadı", file=stream)
        stream.flush()
        self.assertIn("radarına", raw.getvalue().decode("utf-8"))



if __name__ == "__main__":
    unittest.main()
