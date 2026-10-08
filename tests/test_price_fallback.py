"""The fallback price providers that step in when yfinance is cut off.

This behaviour had no test because the behaviour did not exist:
`_download_batch` depended on a single provider and, if it came back empty, the
whole portfolio silently fell back to a stale cache.

The tests focus on two contracts:
  1. The fallback provider speaks IN YFINANCE'S UNIT SPACE -- the downstream
     lira-conversion maths (the USDTRY multiplication, ounce-to-gram) works
     unchanged.
  2. The price's source is reported CORRECTLY. Calling a price from a fallback
     "Yahoo Finance" would be showing the user the wrong origin.

"""
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo


ISTANBUL = ZoneInfo("Europe/Istanbul")

WEEKDAY_NOON = datetime(2026, 7, 22, 12, 0, tzinfo=ISTANBUL)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class PriceFallbackTest(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.db_patch = mock.patch("database.db.DB_NAME", self.db_path)
        self.db_patch.start()
        from database.init_db import initialize_database
        initialize_database()

        from services import price_service
        with price_service._inflight_lock:
            price_service._inflight.clear()

    def tearDown(self):
        self.db_patch.stop()
        os.unlink(self.db_path)


    def test_coingecko_fallback_returns_usd_not_try(self):
        """CRITICAL: CoinGecko can also give TRY, but yfinance gives USD.

        Returning the wrong unit silently produces a portfolio value inflated
        about 35x, because downstream multiplies the result by USDTRY as
        well.
        """
        from services import price_providers

        with mock.patch("requests.get", return_value=_Response(
                {"bitcoin": {"usd": 95_000.0}})) as get:
            out = price_providers.fetch_fallback_prices(["BTC-USD"])

        self.assertEqual(out["BTC-USD"], (95_000.0, "CoinGecko"))
        self.assertEqual(get.call_args.kwargs["params"]["vs_currencies"], "usd")

    def test_frankfurter_fallback_inverts_rate_to_try_per_unit(self):
        """Frankfurter with `from=TRY` gives how many USD one lira is worth; what is
        wanted is the inverse (how many lira one USD is).
        """
        from services import price_providers

        with mock.patch("requests.get", return_value=_Response(
                {"rates": {"USD": 0.025}})):
            out = price_providers.fetch_fallback_prices(["USDTRY=X"])

        price, source = out["USDTRY=X"]
        self.assertAlmostEqual(price, 40.0)
        self.assertEqual(source, "Frankfurter (ECB)")

    def test_uncovered_tickers_are_skipped_not_faked(self):
        """There is NO fallback for BIST and GC=F -- a documented boundary."""
        from services import price_providers

        with mock.patch("requests.get") as get:
            out = price_providers.fetch_fallback_prices(["THYAO.IS", "GC=F"])

        self.assertEqual(out, {})
        get.assert_not_called()

    def test_one_provider_failing_does_not_block_the_other(self):
        from services import price_providers
        import requests

        def _get(url, **_kwargs):
            if "coingecko" in url:
                raise requests.RequestException("down")
            return _Response({"rates": {"USD": 0.025}})

        with mock.patch("requests.get", side_effect=_get):
            out = price_providers.fetch_fallback_prices(
                ["BTC-USD", "USDTRY=X"])

        self.assertNotIn("BTC-USD", out)
        self.assertIn("USDTRY=X", out)


    def _fetch(self, symbols, yahoo_result, fallback_result):
        """Runs the fetch and reads the result FROM THE CACHE.

        The callback is not inspected -- delivery to the interface thread is the
        scheduler's concern. `tests/test_price_service.py` verifies through the
        cache for the same reason.
        """
        from services import price_service

        with (
            mock.patch.object(price_service, "_now",
                              return_value=WEEKDAY_NOON),
            mock.patch.object(price_service, "_download_batch",
                              return_value=dict(yahoo_result)),
            mock.patch("services.price_providers.fetch_fallback_prices",
                       return_value=dict(fallback_result)),
        ):
            thread = price_service.fetch_prices_async(
                symbols, None, force_refresh=True)
            if thread is not None:
                thread.join(timeout=10)
        return price_service.get_cached_prices(
            [symbol for symbol, _kind in symbols])

    def test_fallback_fills_the_gap_yfinance_left(self):
        prices = self._fetch(
            [("BTC", "CRYPTO")],
            yahoo_result={"USDTRY=X": 40.0},          # kripto YOK
            fallback_result={"BTC-USD": (95_000.0, "CoinGecko")},
        )

        self.assertAlmostEqual(prices["BTC"], 3_800_000.0)

    def test_usdtry_fallback_rescues_crypto_conversion(self):
        """USDTRY is the keystone: if it falls, neither crypto NOR gold can be priced."""
        prices = self._fetch(
            [("BTC", "CRYPTO")],
            yahoo_result={"BTC-USD": 95_000.0},       # USDTRY YOK
            fallback_result={"USDTRY=X": (40.0, "Frankfurter (ECB)")},
        )
        self.assertAlmostEqual(prices["BTC"], 3_800_000.0)

    def test_no_fallback_call_when_yfinance_covered_everything(self):
        from services import price_service

        with (
            mock.patch.object(price_service, "_now",
                              return_value=WEEKDAY_NOON),
            mock.patch.object(price_service, "_download_batch",
                              return_value={"BTC-USD": 95_000.0,
                                            "USDTRY=X": 40.0}),
            mock.patch("services.price_providers.fetch_fallback_prices") as fb,
        ):
            thread = price_service.fetch_prices_async(
                [("BTC", "CRYPTO")], None, force_refresh=True)
            if thread is not None:
                thread.join(timeout=10)
        fb.assert_not_called()

    # ── Source reporting ────────────────────────────────────────────────

    def test_status_reports_the_provider_that_actually_answered(self):
        from services import price_service

        self._fetch(
            [("BTC", "CRYPTO")],
            yahoo_result={"USDTRY=X": 40.0},
            fallback_result={"BTC-USD": (95_000.0, "CoinGecko")},
        )
        status = price_service.get_price_status(
            "BTC", "CRYPTO", now=WEEKDAY_NOON)

        self.assertEqual(status.source, "CoinGecko + Yahoo Finance")

    def test_status_stays_yahoo_when_yahoo_answered(self):
        from services import price_service

        self._fetch(
            [("BTC", "CRYPTO")],
            yahoo_result={"BTC-USD": 95_000.0, "USDTRY=X": 40.0},
            fallback_result={},
        )
        status = price_service.get_price_status(
            "BTC", "CRYPTO", now=WEEKDAY_NOON)
        self.assertEqual(status.source, "Yahoo Finance")

    # ── Migration ───────────────────────────────────────────────────────

    def test_rows_written_before_the_source_column_read_back_as_yahoo(self):
        """Old profiles have no `source` column. Those rows came from yfinance (it
        was the only provider at the time) and must be reported as such -- and
        adding the column must not lose the existing data.
        """
        from services import price_service


        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DROP TABLE IF EXISTS asset_price_cache")
            conn.execute("""
                CREATE TABLE asset_price_cache (
                    symbol TEXT PRIMARY KEY,
                    price REAL NOT NULL,
                    asset_type TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "INSERT INTO asset_price_cache VALUES (?, ?, ?, ?)",
                ("ASELS", 245.5, "STOCK", WEEKDAY_NOON.isoformat()),
            )
            conn.commit()

        status = price_service.get_price_status(
            "ASELS", "STOCK", now=WEEKDAY_NOON)
        self.assertEqual(status.source, "Yahoo Finance")
        self.assertIsNotNone(status.price)

        with closing(sqlite3.connect(self.db_path)) as conn:
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(asset_price_cache)")
            }
        self.assertIn("source", columns)


if __name__ == "__main__":
    unittest.main()
