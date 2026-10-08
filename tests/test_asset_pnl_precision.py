"""The behaviour lock and precision regression for `calculate_pnl`.

WHY IT EXISTS: this function had NO test at all. It produces every profit/loss,
current-value and cost number on the portfolio screen, and it did four
consecutive binary floating-point operations before applying
`round(..., 2)` at the end.

The two classes are deliberately separate:

  * `PnlBehaviourLock` -- everything the Decimal migration MUST NOT CHANGE.
    These tests must give the same result both before and after the migration;
    they are the evidence for the migration's claim that it "preserves
    behaviour".

  * `PnlBinaryArtefact` -- the kurus errors the migration is expected to FIX.
    These are RED before the migration and green after. The only honest way to
    show that a migration really gained something is to write the gain as a red
    test first.

Note that the `signal` decision is made from the raw (unrounded) ratio: moving
to the rounded percentage would show an asset with a 0.004 gain as "breakeven".
`test_signal_comes_from_the_unrounded_ratio` locks that down.

"""

import unittest

from services.asset_service import calculate_pnl


class PnlBehaviourLock(unittest.TestCase):
    """The Decimal migration must change NONE of these values."""

    def test_profit_case(self):
        result = calculate_pnl(150.0, 100.0, 10.0)
        self.assertEqual(result["total_cost"], 1000.0)
        self.assertEqual(result["total_value"], 1500.0)
        self.assertEqual(result["pnl_amount"], 500.0)
        self.assertEqual(result["pnl_pct"], 50.0)
        self.assertEqual(result["signal"], "profit")

    def test_loss_case(self):
        result = calculate_pnl(80.0, 100.0, 10.0)
        self.assertEqual(result["total_cost"], 1000.0)
        self.assertEqual(result["total_value"], 800.0)
        self.assertEqual(result["pnl_amount"], -200.0)
        self.assertEqual(result["pnl_pct"], -20.0)
        self.assertEqual(result["signal"], "loss")

    def test_breakeven_case(self):
        result = calculate_pnl(100.0, 100.0, 10.0)
        self.assertEqual(result["pnl_amount"], 0.0)
        self.assertEqual(result["pnl_pct"], 0.0)
        self.assertEqual(result["signal"], "breakeven")

    def test_zero_purchase_price_reports_breakeven_despite_a_gain(self):
        """The STRANGENESS of the current behaviour, deliberately preserved.

        `purchase_price = 0` defines no ratio (division by zero), and the code
        takes the ratio as 0.0 and says "breakeven" -- while `pnl_amount` is
        1,500 lira. That can be misleading, but CHANGING it is not this PR's
        job: mixing a precision migration with a product decision into the same
        commit makes both harder to review. The test guarantees the migration
        did not change it by accident.
        """
        result = calculate_pnl(150.0, 0.0, 10.0)
        self.assertEqual(result["total_cost"], 0.0)
        self.assertEqual(result["total_value"], 1500.0)
        self.assertEqual(result["pnl_amount"], 1500.0)
        self.assertEqual(result["pnl_pct"], 0.0)
        self.assertEqual(result["signal"], "breakeven")

    def test_high_precision_quantity_rounds_money_to_zero(self):
        """A crypto quantity (1e-8) -- the money fields zero at the kurus, the ratio remains."""
        result = calculate_pnl(250.0, 200.0, 0.00000001)
        self.assertEqual(result["total_cost"], 0.0)
        self.assertEqual(result["total_value"], 0.0)
        self.assertEqual(result["pnl_amount"], 0.0)
        self.assertEqual(result["pnl_pct"], 25.0)
        self.assertEqual(result["signal"], "profit")

    def test_large_but_valid_values(self):
        result = calculate_pnl(1e9, 999999999.0, 1000.0)
        self.assertEqual(result["total_value"], 1000000000000.0)
        self.assertEqual(result["total_cost"], 999999999000.0)
        self.assertEqual(result["pnl_amount"], 1000.0)
        self.assertEqual(result["signal"], "profit")

    def test_signal_comes_from_the_unrounded_ratio(self):
        """A gain is a gain even if the ratio stays BELOW the second decimal of the percentage.

        The ratio 1e9 / 999,999,999 is 0.0000001% -- rounded it shows as 0.00,
        but `signal` must stay "profit". If the decision moves to the rounded
        percentage this test breaks.
        """
        result = calculate_pnl(1e9, 999999999.0, 1000.0)
        self.assertEqual(result["pnl_pct"], 0.0)
        self.assertEqual(result["signal"], "profit")

    def test_production_shaped_inputs_return_floats(self):
        """The real callers always pass floats; the return must stay float too.

        `asset["purchase_price"]` and `asset["quantity"]` are produced with
        `float(decrypt(...))`, and `current_price` comes from a REAL column --
        so all three inputs are floats in production. The UI and the cache are
        written against that type.
        """
        result = calculate_pnl(150.0, 100.0, 10.0)
        for key in ("pnl_amount", "pnl_pct", "total_value", "total_cost"):
            self.assertIsInstance(result[key], float, f"{key} float olmalı")
        self.assertIsInstance(result["signal"], str)


class PnlBinaryArtefact(unittest.TestCase):
    """RED before the migration, green after: the evidence of the gain."""

    def test_sub_kurus_unit_price_does_not_lose_a_kurus(self):
        """0.045 x 15 = 0.675 -- rounded to the kurus it must be 0.68.

        In binary floating point 0.045*15 comes out as 0.6749999999999999 and
        `round()` brings that down to 0.67. One kurus, but its source is
        representation error: the number the user entered was 0.045, not
        0.04499999... `Decimal(str(...))` takes the input as it was written.
        """
        result = calculate_pnl(0.05, 0.045, 15.0)
        self.assertEqual(result["total_cost"], 0.68)

    def test_fractional_unit_price_keeps_the_half_kurus(self):
        """1.005 x 3 = 3.015 -- by policy, 3.02.

        THIS TEST IS THE RECORD OF A MISTAKE OF MINE: I first wrote this case
        as "behaviour to be preserved" and took the expectation from the
        current output (3.01). That was wrong -- the current output was itself
        the artefact: because 1.005*3 is 3.0149999999999997 in binary
        representation, `round()` never saw the boundary at all. Measuring the
        current behaviour and writing it down as the expectation is the easiest
        way to turn a bug into a contract; when writing a characterisation test
        one must also check whether the measured value is the EXACT result.
        """
        result = calculate_pnl(1.005, 1.0, 3.0)
        self.assertEqual(result["total_cost"], 3.0)
        self.assertEqual(result["total_value"], 3.02)
        self.assertEqual(result["pnl_amount"], 0.02)
        self.assertEqual(result["pnl_pct"], 0.5)
        self.assertEqual(result["signal"], "profit")

    def test_half_cent_boundary_rounds_by_policy_not_by_representation(self):
        """2.675 is exactly on the half-kurus boundary.

        Our policy is ROUND_HALF_EVEN (`utils/financial_decimal.py`) and for
        2.675 the result is 2.68. `round()` also uses HALF_EVEN -- the
        difference is not in the mode but in the INPUT: because the float 2.675
        is really 2.67499999..., `round()` never sees the boundary and gives
        2.67.
        """
        result = calculate_pnl(3.0, 2.675, 1.0)
        self.assertEqual(result["total_cost"], 2.68)


class PnlNonFiniteInput(unittest.TestCase):
    """The one DELIBERATE behaviour change, kept in its own class.

    Non-finite input used to return `nan`/`inf` silently -- and moreover said
    "breakeven" for `nan` and "profit" for `inf`. Both leaked to the screen and
    into the `total +=` sums; the read-side form of the corruption class
    already closed on the write path.

    Raising WAS NOT AN OPTION: `asset_service.load_assets_with_prices` and
    `price_service.enrich_assets_from_cache` make this call in an unguarded
    loop, so one broken row would bring down the WHOLE portfolio load. Instead
    it returns the shape the callers ALREADY produce and handle for an asset
    that cannot be priced.
    """

    def _assert_error_shape(self, result):
        self.assertEqual(result["signal"], "error")
        for key in ("pnl_amount", "pnl_pct", "total_value", "total_cost"):
            self.assertIsNone(result[key], f"{key} None olmalı")

    def test_nan_price_no_longer_reports_breakeven(self):
        self._assert_error_shape(calculate_pnl(float("nan"), 100.0, 10.0))

    def test_infinite_quantity_no_longer_reports_profit(self):
        self._assert_error_shape(calculate_pnl(150.0, 100.0, float("inf")))

    def test_missing_value_does_not_raise(self):
        """It used to raise `TypeError`; that would bring down the loop again."""
        self._assert_error_shape(calculate_pnl(150.0, None, 10.0))


if __name__ == "__main__":
    unittest.main()
