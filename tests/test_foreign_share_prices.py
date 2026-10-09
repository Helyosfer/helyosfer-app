"""A share that is not on BIST is priced on its own exchange and put into lira."""

import unittest


def _share(asset_id, code, kind="Hisse"):
    return {"id": asset_id, "asset_code": code, "asset_type": kind,
            "asset_name": code, "purchase_price": 1.0, "quantity": 1.0}


class ForeignSharePricesTest(unittest.TestCase):
    def _prices(self, assets, found_on_bist=(), quotes=None, rates=None):
        from services.asset_service import foreign_share_prices, get_ticker_candidates

        quotes = quotes or {}
        rates = {"TRY": 1.0, "USD": 40.0, **(rates or {})}
        self.asked = []
        ticker_by_id = {
            a["id"]: get_ticker_candidates(a["asset_code"], a["asset_type"])[0] for a in assets
        }
        raw = {ticker_by_id[asset_id]: 100.0 for asset_id in found_on_bist}

        def quote(symbol):
            self.asked.append(symbol)
            return quotes.get(symbol)

        return foreign_share_prices(assets, ticker_by_id, raw, quote=quote, rate=rates.get)

    def test_a_share_found_on_bist_is_not_looked_up_again(self):
        prices = self._prices([_share(1, "THYAO")], found_on_bist=[1])
        self.assertEqual((prices, self.asked), ({}, []))

    def test_a_share_listed_elsewhere_is_converted_into_lira(self):
        prices = self._prices([_share(1, "AAPL")], quotes={"AAPL": (250.0, "USD")})
        self.assertEqual(prices, {1: 10000.0})
        self.assertEqual(self.asked, ["AAPL"])

    def test_the_exchanges_own_currency_is_used(self):
        prices = self._prices(
            [_share(1, "SAP")], quotes={"SAP": (200.0, "EUR")}, rates={"EUR": 45.0})
        self.assertEqual(prices, {1: 9000.0})

    def test_a_price_that_cannot_be_converted_is_left_out(self):
        prices = self._prices([_share(1, "NESN")], quotes={"NESN": (90.0, "CHF")})
        self.assertEqual(prices, {})

    def test_an_unknown_symbol_is_left_out(self):
        self.assertEqual(self._prices([_share(1, "NOSUCHXYZ")]), {})

    def test_the_same_symbol_is_asked_for_once(self):
        prices = self._prices(
            [_share(1, "AAPL"), _share(2, "aapl")], quotes={"AAPL": (250.0, "USD")})
        self.assertEqual(prices, {1: 10000.0, 2: 10000.0})
        self.assertEqual(self.asked, ["AAPL"])

    def test_only_shares_are_tried_this_way(self):
        prices = self._prices(
            [_share(1, "USD", "Döviz"), _share(2, "BTC", "Kripto")],
            quotes={"USD": (1.0, "USD"), "BTC": (1.0, "USD")})
        self.assertEqual((prices, self.asked), ({}, []))

    def test_a_symbol_typed_with_its_exchange_has_no_second_form(self):
        prices = self._prices([_share(1, "THYAO.IS")])
        self.assertEqual((prices, self.asked), ({}, []))


if __name__ == "__main__":
    unittest.main()
