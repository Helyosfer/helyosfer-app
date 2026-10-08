"""The portfolio market-value total must not lose a kurus.

WHY IT EXISTS: `fetch_active_non_try_total` computed each asset's value with
`float(quantity) * float(price)` and summed them in a float accumulator. The
same class as the one closed in `calculate_pnl`: when the product falls on a
rounding boundary, the binary representation swallows the half kurus.

Verified by measurement, and the important point is this: these cases are not
invented but sit INSIDE Helysofer's OWN precision policy -- 8 digits for a
crypto quantity, 6 for a share, two or three decimals for prices.

    15 crypto x 0.045 lira      = 0.675  ->  shown as 0.67, should be 0.68
    3 shares  x 1.005 lira      = 3.015  ->  shown as 3.01, should be 3.02
    0.00000015 x 4,500,000 lira = 0.675  ->  shown as 0.67, should be 0.68

The tests drive THE REAL PATH rather than the helper: the assets are written to
the database, the price cache is filled, `fetch_active_non_try_total` is called
and the result the callback gives is read.

"""

import os
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock


class PortfolioTotalPrecision(unittest.TestCase):

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory(prefix="helysofer-porttotal-")
        root = Path(self.tempdir.name)
        self.db_path = root / "finance.db"
        self.db_patch = mock.patch("database.db.DB_NAME", str(self.db_path))
        self.key_patch = mock.patch(
            "utils.crypto._get_aead_key", return_value=os.urandom(32)
        )
        self.db_patch.start()
        self.key_patch.start()
        self.addCleanup(self.tempdir.cleanup)
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.key_patch.stop)

        from database.init_db import initialize_database
        initialize_database()


    def _add_asset(self, name, code, kind, price, quantity):
        from database.db import insert_asset
        insert_asset(name, code, kind, price, quantity)

    def _total_for(self, assets, prices):
        """assets: [(name, code, type, purchase, quantity)] . prices: {code: price}

        The price cache is written directly; there is no network. Because
        `fetch_active_non_try_total` opens a background thread, the result is
        awaited with an Event.
        """
        for asset in assets:
            self._add_asset(*asset)

        import services.asset_service as asset_service

        done = threading.Event()
        captured = {}

        def callback(result):
            captured.update(result)
            done.set()

        with mock.patch(
            "services.price_service.get_cached_prices", return_value=dict(prices)
        ), mock.patch("services.price_service.fetch_prices_async", return_value=None):
            asset_service.fetch_active_non_try_total(callback)
            self.assertTrue(done.wait(timeout=10), "toplam hesabı zamanında bitmedi")
        return captured

    def _assert_total_kurus(self, result, expected):
        """The kurus displayed must equal the kurus of the exact Decimal result.

        The comparison is made through the formatting the UI uses
        (`f"{value:,.2f}"`), because that is the number
        the user sees. Reading the service's `total` field raw could have
        hidden the error at the boundary.
        """
        shown = f"{result['total']:,.2f}"
        self.assertEqual(
            shown, expected,
            f"gösterilen toplam {shown}, beklenen {expected} "
            f"(ham değer: {result['total']!r})",
        )


    def test_crypto_quantity_times_sub_kurus_price(self):
        """15 x 0,045 = 0,675 -> 0,68."""
        result = self._total_for(
            [("Coin", "AAA-USD", "Kripto", 0.045, 15.0)],
            {"AAA-USD": 0.045},
        )
        self._assert_total_kurus(result, "0.68")

    def test_equity_quantity_times_fractional_price(self):
        """3 x 1,005 = 3,015 -> 3,02."""
        result = self._total_for(
            [("Hisse", "BBB", "Hisse", 1.005, 3.0)],
            {"BBB": 1.005},
        )
        self._assert_total_kurus(result, "3.02")

    def test_high_precision_crypto_quantity_times_large_price(self):
        """0,00000015 x 4.500.000 = 0,675 -> 0,68."""
        result = self._total_for(
            [("Coin", "CCC-USD", "Kripto", 1.0, 0.00000015)],
            {"CCC-USD": 4_500_000.0},
        )
        self._assert_total_kurus(result, "0.68")


    def test_ten_assets_match_the_decimal_reference(self):
        assets, prices, reference = [], {}, Decimal(0)
        for index in range(10):
            code = f"D{index:02d}"
            quantity = Decimal("0.045") * (index + 1)
            price = Decimal("15.005")
            assets.append(("Coin", code, "Kripto", float(price), float(quantity)))
            prices[code] = float(price)
            reference += quantity * price
        result = self._total_for(assets, prices)
        self._assert_total_kurus(
            result, f"{reference.quantize(Decimal('0.01')):,.2f}")

    def test_hundred_assets_match_the_decimal_reference(self):
        assets, prices, reference = [], {}, Decimal(0)
        for index in range(100):
            code = f"E{index:03d}"
            quantity = Decimal("0.00000015") * (index + 1)
            price = Decimal("4500000.00")
            assets.append(("Coin", code, "Kripto", 1.0, float(quantity)))
            prices[code] = float(price)
            reference += quantity * price
        result = self._total_for(assets, prices)
        self._assert_total_kurus(
            result, f"{reference.quantize(Decimal('0.01')):,.2f}")


    def test_progress_and_final_totals_agree(self):
        """The last intermediate total and the final total must show THE SAME financial value.

        What is protected is not "a bit-for-bit identical accumulator" -- that
        was only a detail of the old implementation. The contract is that the
        two represent the same money; both must go through the same
        conversion.
        """
        import services.asset_service as asset_service

        for index in range(3):
            self._add_asset("Coin", f"F{index}", "Kripto", 0.045, 15.0)

        seen = []
        done = threading.Event()
        final = {}

        def progress(result):
            seen.append(result)

        def callback(result):
            final.update(result)
            done.set()

        prices = {f"F{index}": 0.045 for index in range(3)}
        with mock.patch(
            "services.price_service.get_cached_prices", return_value=prices
        ), mock.patch("services.price_service.fetch_prices_async", return_value=None):
            asset_service.fetch_active_non_try_total(callback, progress)
            self.assertTrue(done.wait(timeout=10))

        self.assertTrue(seen, "hiç progress olayı gelmedi")
        self.assertEqual(seen[0]["total"], 0.0, "ilk progress 0,0 olmalı")
        self.assertIsInstance(final["total"], float, "public tip float kalmalı")
        for event in seen:
            self.assertIsInstance(event["total"], float)
        self.assertEqual(
            f"{seen[-1]['total']:,.2f}", f"{final['total']:,.2f}",
            "son ara toplam ile nihai toplam aynı parayı göstermiyor",
        )
        self.assertEqual(final["priced_count"], 3)
        self.assertEqual(final["asset_count"], 3)

    def test_a_non_finite_price_does_not_kill_the_background_thread(self):
        """An infinite price is NOT THEORETICAL: the existing filter lets it through.

        `_fetch_live_try_prices` and `price_providers` filter the price with
        `if value is not None and float(value) > 0` -- and `float("inf") > 0` is
        TRUE. So an infinite price from a broken provider can be written to the
        cache.

        The total now uses `decimal_from()`, which raises `ValueError` on a
        non-finite value. This loop runs on a background thread and is
        unguarded; had the exception leaked out, the callback would never be
        called and the interface would wait forever. A broken asset must be
        skipped the same way as an unpriceable one, and the REMAINING total must
        come out correct.
        """
        result = self._total_for(
            [("Coin", "H01", "Kripto", 0.045, 15.0),
             ("Bozuk", "H02", "Kripto", 1.0, 1.0)],
            {"H01": 0.045, "H02": float("inf")},
        )
        self._assert_total_kurus(result, "0.68")
        self.assertEqual(result["priced_count"], 1, "bozuk varlık sayılmamalı")
        self.assertEqual(result["asset_count"], 2)
        self.assertTrue(result["complete"], "callback tamamlanmadan döndü")

    def test_unpriced_assets_are_skipped_without_breaking_the_total(self):
        result = self._total_for(
            [("Coin", "G01", "Kripto", 0.045, 15.0),
             ("Coin", "G02", "Kripto", 1.0, 1.0)],
            {"G01": 0.045},
        )
        self._assert_total_kurus(result, "0.68")
        self.assertEqual(result["priced_count"], 1)
        self.assertEqual(result["asset_count"], 2)


if __name__ == "__main__":
    unittest.main()
