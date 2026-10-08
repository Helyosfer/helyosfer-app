"""NaN/Inf values from external price providers must never get in.

THE MEASURED DEFECT: all three price entry points used the pattern
`value is not None and float(value) > 0`.

    >>> float("inf") > 0
    True

So an infinite price PASSES that gate. Because `json.loads` accepts the
`Infinity` and `NaN` constants by default, a broken or hostile provider
response can produce this directly. The consequence is not merely visual:

  * `_store_cache` WRITES the infinity into `asset_price_cache` -- so the value
    becomes persistent and is read until the TTL expires, even after the
    provider recovers.
  * `_read_cache` does not test finiteness while reading, so an already
    poisoned row enters the portfolio total and `inf * quantity` makes the
    whole total `inf`.

This file pins the guard ON THE PRODUCTION PATHS: the provider parsing
functions, the legacy `asset_service` path, the cache write and the cache read.

"""
import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest import mock

from services.price_guard import finite_positive_price


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FinitePositivePriceContractTest(unittest.TestCase):
    """The pure contract of the single normalisation boundary."""

    def test_non_finite_and_non_positive_values_are_refused(self):
        for value in (
            float("nan"), float("inf"), float("-inf"),
            "nan", "inf", "-inf", "Infinity", "NaN",
            1e400,
            0, 0.0, "0", -1, -0.5, "-3",
            None, "", "  ", "abc", [], {}, object(),
            True, False,
        ):
            with self.subTest(value=repr(value)):
                self.assertIsNone(finite_positive_price(value))

    def test_ordinary_prices_pass_through_as_floats(self):
        for value, expected in (
            (95_000.0, 95_000.0),
            (12, 12.0),
            ("12.5", 12.5),
            (0.00000001, 0.00000001),
        ):
            with self.subTest(value=repr(value)):
                result = finite_positive_price(value)
                self.assertIsInstance(result, float)
                self.assertEqual(result, expected)
                self.assertTrue(math.isfinite(result))


class ProviderIngressTest(unittest.TestCase):
    """The REAL provider parsing paths."""

    def test_coingecko_infinity_is_dropped_but_the_batch_survives(self):
        from services import price_providers

        with mock.patch("requests.get", return_value=_Response({
            "bitcoin": {"usd": float("inf")},
            "ethereum": {"usd": 3_000.0},
        })):
            out = price_providers.fetch_fallback_prices(["BTC-USD", "ETH-USD"])

        self.assertNotIn("BTC-USD", out)
        self.assertEqual(out["ETH-USD"], (3_000.0, "CoinGecko"))

    def test_coingecko_nan_is_dropped(self):
        from services import price_providers

        with mock.patch("requests.get", return_value=_Response(
                {"bitcoin": {"usd": float("nan")}})):
            out = price_providers.fetch_fallback_prices(["BTC-USD"])
        self.assertEqual(out, {})

    def test_frankfurter_non_finite_rate_is_dropped(self):
        from services import price_providers

        for rate in (float("inf"), float("nan"), float("-inf"), 0):
            with self.subTest(rate=rate):
                with mock.patch("requests.get", return_value=_Response(
                        {"rates": {"USD": rate}})):
                    out = price_providers.fetch_fallback_prices(["USDTRY=X"])
                self.assertEqual(out, {})

    def test_frankfurter_valid_rate_still_inverts(self):
        from services import price_providers

        with mock.patch("requests.get", return_value=_Response(
                {"rates": {"USD": 0.025}})):
            out = price_providers.fetch_fallback_prices(["USDTRY=X"])
        self.assertAlmostEqual(out["USDTRY=X"][0], 40.0)


class LegacyAssetServiceIngressTest(unittest.TestCase):
    """`asset_service._fetch_live_try_prices` must be protected with the same discipline."""

    def test_non_finite_crypto_price_is_dropped(self):
        from services import asset_service

        assets = [{"asset_code": "BTC-USD", "asset_type": "Kripto"}]
        with mock.patch("requests.get", return_value=_Response(
                {"bitcoin": {"try": float("inf")}})):
            prices = asset_service._fetch_live_try_prices(assets)
        self.assertEqual(prices, {})

    def test_non_finite_fiat_rate_is_dropped(self):
        from services import asset_service

        assets = [{"asset_code": "USDTRY=X", "asset_type": "Döviz"}]
        with mock.patch("requests.get", return_value=_Response(
                {"rates": {"USD": float("nan")}})):
            prices = asset_service._fetch_live_try_prices(assets)
        self.assertEqual(prices, {})

    def test_valid_price_still_arrives(self):
        from services import asset_service

        assets = [{"asset_code": "BTC-USD", "asset_type": "Kripto"}]
        with mock.patch("requests.get", return_value=_Response(
                {"bitcoin": {"try": 3_500_000.0}})):
            prices = asset_service._fetch_live_try_prices(assets)
        self.assertEqual(prices, {"BTC-USD": 3_500_000.0})


class PriceCacheBoundaryTest(unittest.TestCase):
    """The cache must test finiteness BOTH when writing AND when reading."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_patch = mock.patch("database.db.DB_NAME", self.db_path)
        self.db_patch.start()
        self.addCleanup(os.unlink, self.db_path)
        self.addCleanup(self.db_patch.stop)
        from database.init_db import initialize_database

        initialize_database()

    def _rows(self):
        with closing(sqlite3.connect(self.db_path)) as conn:
            return conn.execute(
                "SELECT symbol, price FROM asset_price_cache"
            ).fetchall()

    def test_non_finite_price_is_never_written_to_the_cache(self):
        from services import price_service

        price_service._store_cache(
            {"BTC-USD": float("inf"), "ETH-USD": float("nan"),
             "XRP-USD": 2.5},
            {"BTC-USD": "Kripto", "ETH-USD": "Kripto", "XRP-USD": "Kripto"},
        )
        self.assertEqual(self._rows(), [("XRP-USD", 2.5)])

    def test_a_previously_poisoned_row_is_not_handed_to_consumers(self):
        """A corrupt row written by older versions can still be read today."""
        from services import price_service

        price_service._store_cache({"BTC-USD": 100.0}, {"BTC-USD": "Kripto"})
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE asset_price_cache SET price = ? WHERE symbol = ?",
                (float("inf"), "BTC-USD"),
            )
            conn.commit()

        self.assertIsNone(price_service.get_cached_price("BTC-USD"))
        self.assertEqual(price_service.get_cached_prices(["BTC-USD"]), {})

    def test_a_poisoned_row_cannot_reach_a_portfolio_total(self):
        from services import price_service

        price_service._store_cache({"BTC-USD": 100.0}, {"BTC-USD": "Kripto"})
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute(
                "UPDATE asset_price_cache SET price = ? WHERE symbol = ?",
                (float("inf"), "BTC-USD"),
            )
            conn.commit()

        enriched = price_service.enrich_assets_from_cache([{
            "asset_code": "BTC-USD",
            "asset_type": "Kripto",
            "purchase_price": 50.0,
            "quantity": 2.0,
        }])
        for asset in enriched:
            for value in asset.values():
                if isinstance(value, float):
                    self.assertTrue(
                        math.isfinite(value),
                        f"sonlu olmayan değer tüketiciye ulaştı: {asset}",
                    )

    def test_valid_cache_round_trip_is_unchanged(self):
        from services import price_service

        price_service._store_cache({"BTC-USD": 95_000.0}, {"BTC-USD": "Kripto"})
        self.assertEqual(price_service.get_cached_price("BTC-USD"), 95_000.0)


if __name__ == "__main__":
    unittest.main()
