"""Fallback price providers that step in when yfinance is cut off.

WHY: `price_service._download_batch` depended on a single provider (yfinance).
If that call came back empty the whole portfolio silently fell back to a stale
cache, and the user only found out by noticing the prices were not updating.

DESIGN -- this module DELIBERATELY speaks in yfinance's unit space: it fills
the return of `_download_batch` under the same contract, so no branch of the
lira-conversion maths inside `fetch_prices_async` (the USDTRY multiplication,
the ounce-to-gram division, the gold multiplier) changes. Whether a symbol
comes from CoinGecko or from yfinance, everything downstream sees the same
number.

SCOPE -- honest boundaries:
  * `XXX-USD`  (crypto)   -> CoinGecko, in USD          ok
  * `XXXTRY=X` (currency) -> Frankfurter, lira per unit ok
  * `GC=F`     (gold)     -> NO fallback
  * `XXXX.IS`  (BIST)     -> NO fallback
For the last two there is no free source already proven in the repository;
rather than invent a provider they were left out of scope. Backing up
`USDTRY=X` still rescues gold INDIRECTLY: because the gold price is converted
to lira via `GC=F * USDTRY`, when USDTRY drops out of yfinance and is rescued
here, the conversion can complete even if the ounce price comes from cache.

Both providers were already in use inside
`services/asset_service.py::_fetch_live_try_prices`; the difference here is
that the result is returned in yfinance's unit rather than in lira.

"""

import re

from services.price_guard import finite_positive_price
from utils.logging_config import get_logger


_TIMEOUT = 8

SOURCE_YAHOO = "Yahoo Finance"
SOURCE_COINGECKO = "CoinGecko"
SOURCE_FRANKFURTER = "Frankfurter (ECB)"

_FIAT_TICKER = re.compile(r"^([A-Z]{3})TRY=X$")
_CRYPTO_TICKER = re.compile(r"^([A-Z0-9]{2,10})-(USD|USDT)$")


def _coingecko_ids_for(symbols):
    from services.asset_service import _coingecko_id_for

    out = {}
    for symbol in symbols:
        coin_id = _coingecko_id_for(symbol)
        if coin_id:
            out[symbol] = coin_id
    return out


def _fetch_crypto_usd(tickers):
    """The USD price from CoinGecko for tickers such as `BTC-USD`."""
    import requests

    wanted = {}
    for ticker in tickers:
        match = _CRYPTO_TICKER.match(ticker)
        if match:
            wanted[ticker] = ticker
    if not wanted:
        return {}

    ids = _coingecko_ids_for(wanted.values())
    if not ids:
        return {}

    response = requests.get(
        "https://api.coingecko.com/api/v3/simple/price",
        params={
            "ids": ",".join(sorted(set(ids.values()))),


            "vs_currencies": "usd",
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()

    out = {}
    for ticker, symbol in wanted.items():
        coin_id = ids.get(symbol)
        if not coin_id:
            continue


        price = finite_positive_price(payload.get(coin_id, {}).get("usd"))
        if price is not None:
            out[ticker] = price
    return out


def _fetch_fiat_try(tickers):
    """The lira value of one unit from Frankfurter, for tickers such as `USDTRY=X`."""
    import requests

    bases = {}
    for ticker in tickers:
        match = _FIAT_TICKER.match(ticker)
        if match and match.group(1) != "TRY":
            bases[ticker] = match.group(1)
    if not bases:
        return {}


    response = requests.get(
        "https://api.frankfurter.app/latest",
        params={"from": "TRY", "to": ",".join(sorted(set(bases.values())))},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    rates = response.json().get("rates", {})

    out = {}
    for ticker, base in bases.items():


        rate = finite_positive_price(rates.get(base))
        if rate is not None:
            inverted = finite_positive_price(1.0 / rate)
            if inverted is not None:
                out[ticker] = inverted
    return out


def fetch_fallback_prices(tickers):
    """Collects prices from the fallback providers for the given yfinance tickers.

    Returns: `{ticker: (price, source)}` -- only the ones ACTUALLY found.
    Tickers outside the scope (BIST, `GC=F`) are skipped silently; that is not
    an error but a documented boundary.

    One provider blowing up does not block the other: each is caught in its
    own block, and a partial result beats no result at all.
    """
    if not tickers:
        return {}

    import requests

    logger = get_logger()
    results = {}
    for label, source, fetch in (
        ("CoinGecko", SOURCE_COINGECKO, _fetch_crypto_usd),
        ("Frankfurter", SOURCE_FRANKFURTER, _fetch_fiat_try),
    ):
        try:
            for ticker, price in fetch(tickers).items():
                results[ticker] = (price, source)
        except (requests.RequestException, ValueError, TypeError,
                KeyError) as exc:


            logger.warning(
                "Yedek fiyat sağlayıcısı %s başarısız: %r", label, exc)
    return results
