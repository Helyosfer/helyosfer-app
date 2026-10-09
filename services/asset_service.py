"""Asset Service -- yfinance-based live price fetching and P/L calculation.

For Borsa Istanbul (BIST) shares the user enters the symbol (for example
'THYAO'); this service automatically appends '.IS' and fetches the data from
Yahoo Finance.

Supported asset_type values (the literal stored strings):
    'Hisse'  -> BIST share  (THYAO -> THYAO.IS)
    'Altın'  -> GC=F or XAUUSD  (fetched in ounces/USD, converted to lira per
                gram -- see _normalize_to_try). Physical gold types such as
                quarter/half/full/ounce have no real yfinance symbol; internal
                GOLD-* symbols are used instead and computed from the gram
                price in lira via a multiplier (see GOLD_TYPE_MULTIPLIERS,
                _fetch_gold_gram_price_try).
    'Tahvil' -> the symbol is sent through directly
    'Döviz'  -> the symbol is sent through directly (USDTRY=X, already in lira)
    'Kripto' -> CODE-USD is fetched and converted to lira (see _normalize_to_try)
    'Diğer'  -> the symbol is sent through directly and not converted

Note: every purchase price in the application (`purchase_price`) is entered by
the user in lira.
Because the yfinance symbols for gold and crypto return USD, without
converting the current price to lira here for those two types the P/L
calculation (services/asset_service.calculate_pnl) would compare a lira
purchase price against a USD current price and produce a completely wrong
result.

"""

import sqlite3
import threading
import time
from datetime import date
from decimal import Decimal
from typing import Any, TypedDict

from services.price_guard import finite_positive_price
from utils.errors import (
    HelysoferError,
    DecryptionError,
    KeyUnavailableError,
)
from utils.financial_decimal import decimal_from, fiat, percentage


def _log():
    """A central rotating log for price/portfolio error records.

    WHY: price-fetch errors in this module were reported
    with `print()`. A packaged Windows application has no console -- so stdout/stderr go nowhere and those
    messages were LOST ENTIRELY. The result: on a complaint such as "the gold
    price will not load on Windows" we had not a single line of evidence.

    The logger is resolved lazily: calling it at module import would create
    the log directory early and could run before the XDG redirection in the
    tests.
    """
    from utils.logging_config import get_logger

    return get_logger()


_PORTFOLIO_CACHE_TABLE = "asset_portfolio_cache"
_PORTFOLIO_CACHE_TTL = 300

GRAMS_PER_TROY_OUNCE = 31.1034768

# -------------------------------------------------------------------------
# GLOBAL PRE-CACHE (WARM-UP)
# -------------------------------------------------------------------------
class _AssetDataCache(TypedDict):
    """The top-level contract of the warm-up snapshot."""
    summary: dict[str, float]
    accounts: list[dict[str, Any]]
    recent: dict[int, list[Any]]
    active_assets_result: dict[str, Any] | None
    ready: bool


_asset_data_cache: _AssetDataCache = {
    "summary": {"cash": 0, "card_debt": 0, "net": 0},
    "accounts": [],
    "recent": {},
    "active_assets_result": None,
    "ready": False
}
_warmup_lock = threading.Lock()
_warmup_generation = 0


_account_cache_stale = False
_financial_data_revision = 0


def mark_account_cache_stale():
    """Ages the account snapshot and the chart revision after a financial write."""
    global _account_cache_stale, _financial_data_revision
    _account_cache_stale = True
    _financial_data_revision += 1


def mark_financial_data_changed():
    """Ages the derived financial results -- WITHOUT TOUCHING the account snapshot.

    `mark_account_cache_stale` is for writes that touch the balance. Some
    changes, however, alter the derived summary without changing the balance
    AT ALL: a category's `importance` field (the main/extra distinction)
    determines `summarize_transactions`'s buckets. Ageing the account snapshot
    for that would be needless work, but without bumping the revision the
    dashboard metric cache would stay STALE.
    """
    global _financial_data_revision
    _financial_data_revision += 1


def get_financial_data_revision():
    """The process-local monotonic revision of the financial data the charts rest on."""
    return _financial_data_revision


def financial_chart_cache_key(period):
    """Produces a safe chart key from the period, the data revision and the calendar day."""
    return (str(period), _financial_data_revision, date.today().isoformat())


def ensure_account_cache_fresh():
    """Refreshes a stale snapshot and returns the CURRENT dictionary.

    The return value matters: `refresh_account_cache_snapshot` REASSIGNS the
    module global, so an old local name taken with
    `from ... import _asset_data_cache` still looks at the old dictionary
    after a refresh. The caller must use what this function returns.

    A cache that has not warmed up yet (ready=False) is not refreshed: the
    startup worker will read the post-write database anyway and will also fill
    the `active_assets_result` field, which needs the network; stepping in
    would drop that to None.
    """
    global _account_cache_stale
    if not _account_cache_stale:
        return _asset_data_cache
    if not (_asset_data_cache and _asset_data_cache.get("ready")):
        return _asset_data_cache
    _account_cache_stale = False
    return refresh_account_cache_snapshot()


def invalidate_asset_data_cache(deleted_account_id=None, deleted_card_debt=0.0):
    """Cancels the old worker and atomically removes the deleted card from the snapshot."""
    global _asset_data_cache, _warmup_generation, _account_cache_stale
    global _financial_data_revision


    _account_cache_stale = False
    _financial_data_revision += 1
    with _warmup_lock:
        _warmup_generation += 1
        previous = _asset_data_cache or {}
        if deleted_account_id is not None:
            account_id = int(deleted_account_id)
            old_summary = previous.get("summary") or {}
            debt = max(0.0, float(deleted_card_debt or 0))
            old_card_debt = float(old_summary.get("card_debt") or 0)
            summary = {
                "cash": float(old_summary.get("cash") or 0),
                "card_debt": max(0.0, old_card_debt - debt),
                "net": float(old_summary.get("net") or 0) + debt,
            }
            accounts_raw = previous.get("accounts")
            accounts_list = accounts_raw if isinstance(accounts_raw, list) else []
            accounts = [
                account for account in accounts_list
                if isinstance(account, dict) and int(account.get("id", 0)) != account_id
            ]
            recent_raw = previous.get("recent")
            recent_dict = recent_raw if isinstance(recent_raw, dict) else {}
            recent = dict(recent_dict)


            recent.pop(account_id, None)
            _asset_data_cache = {
                "summary": summary,
                "accounts": accounts,
                "recent": recent,
                "active_assets_result": previous.get("active_assets_result"),
                "ready": True,
            }
            return

        _asset_data_cache = {
            "summary": {"cash": 0, "card_debt": 0, "net": 0},
            "accounts": [],
            "recent": {},
            "active_assets_result": None,
            "ready": False,
        }

def start_data_warmup(callback=None):
    """Preloads all the data in the background (data warm-up).

    Called at application startup; the data is written into
    _asset_data_cache. Clears the 'data ready' flag.
    """
    global _warmup_generation
    with _warmup_lock:
        _warmup_generation += 1
        generation = _warmup_generation

    def publish(summary, accounts, recent, result):
        with _warmup_lock:
            if generation != _warmup_generation:
                return
            _asset_data_cache["summary"] = summary
            _asset_data_cache["accounts"] = accounts
            _asset_data_cache["recent"] = recent
            _asset_data_cache["active_assets_result"] = result

            _asset_data_cache["ready"] = True
        if callback:
            from utils.ui_dispatch import run_on_main_thread
            run_on_main_thread(callback)

    def worker():
        from services.account_service import AccountService
        from services.transaction_service import TransactionService
        try:
            summary = AccountService.get_net_worth()
            accounts = AccountService.get_accounts()
            recent = {}
            for account in accounts:
                if account["account_type"] == "credit_card" or account.get("has_card_number", False):
                    recent[account["id"]] = TransactionService.get_recent_for_account(account["id"], limit=3)

            def on_non_try(res):
                publish(summary, accounts, recent, res)

            fetch_active_non_try_total(on_non_try)


        except Exception as e:
            _log().error("Data warm-up failed: %s", e, exc_info=True)


            publish(
                {"cash": 0, "card_debt": 0, "net": 0}, [], {},
                {"total": 0.0, "asset_count": 0, "priced_count": 0,
                 "cached_count": 0, "complete": True, "error": str(e)},
            )

    threading.Thread(target=worker, daemon=True).start()


def refresh_account_cache_snapshot():
    """Atomically writes the account balances into the existing cache without waiting on the network.

    Called from the transaction-recording worker, so that ``render_accounts``
    on the UI thread sees the new database state rather than the old startup
    snapshot.
    """
    global _asset_data_cache, _account_cache_stale

    _account_cache_stale = False
    from services.account_service import AccountService
    from services.transaction_service import TransactionService

    summary = AccountService.get_net_worth()
    accounts = AccountService.get_accounts()
    recent = {}
    for account in accounts:
        if (
            account["account_type"] == "credit_card"
            or account.get("has_card_number", False)
        ):
            recent[account["id"]] = TransactionService.get_recent_for_account(
                account["id"], limit=3
            )

    with _warmup_lock:
        previous = _asset_data_cache or {}
        _asset_data_cache = {
            "summary": summary,
            "accounts": accounts,
            "recent": recent,
            "active_assets_result": previous.get("active_assets_result"),
            "ready": True,
        }
    return _asset_data_cache


class _RateCache(TypedDict):
    """A rate/price cache that keeps the VALUE, which may be `None`, separate
    from the TIME stamp, which is always a number.

    Writing a single `dict[str, Any]` would collapse the two into the same
    type; the subtraction `now - cache["time"]` would then pass type checking,
    but so would arithmetic on `cache["rate"]`. Separate fields remind the
    caller that `rate` can be `None`.
    """
    rate: float | None
    time: float


class _PriceCache(TypedDict):
    price: float | None
    time: float


_usdtry_cache: _RateCache = {"rate": None, "time": 0.0}
_USDTRY_CACHE_TTL = 300


GOLD_TYPE_MULTIPLIERS = {
    "GOLD-ONS": GRAMS_PER_TROY_OUNCE,
    "GOLD-CEYREK": 1.75,
    "GOLD-YARIM": 3.5,
    "GOLD-TAM": 7.0,
}

_gold_gram_cache: _PriceCache = {"price": None, "time": 0.0}
_GOLD_GRAM_CACHE_TTL = 300


def _fetch_usdtry_rate() -> float | None:
    """Returns the current USD/TRY rate (1 USD in lira). Cached for 5 minutes;
    on a network error it returns the old value if there is one, and None
    otherwise.
    """
    now = time.time()
    if _usdtry_cache["rate"] is not None and (now - _usdtry_cache["time"]) < _USDTRY_CACHE_TTL:
        return _usdtry_cache["rate"]

    import math
    import yfinance as yf
    try:
        hist = yf.Ticker("USDTRY=X").history(period="5d")
        if not hist.empty:
            rate = float(hist["Close"].dropna().iloc[-1])
            if not math.isnan(rate) and not math.isinf(rate) and rate > 0:
                _usdtry_cache["rate"] = rate
                _usdtry_cache["time"] = now
                return rate
    except Exception:
        _log().exception("USD/TRY kuru çekilemedi")
    return _usdtry_cache["rate"]


def _normalize_to_try(raw_price: float, asset_type: str) -> float | None:
    """Converts a raw price arriving from yfinance in USD into lira.

    For 'Altın' it also applies an ounce-to-gram conversion (the yfinance gold
    symbols quote a price per ounce in USD, while the application works in
    grams and lira). For 'Kripto' only USD is converted to lira. Other types
    already arrive in lira and are left untouched. Returns None if the rate
    cannot be fetched (the caller treats that as "price unavailable").
    """
    usdtry = _fetch_usdtry_rate()
    if usdtry is None:
        return None
    if asset_type == "Altın":
        return (raw_price * usdtry) / GRAMS_PER_TROY_OUNCE
    return raw_price * usdtry  # Kripto


def get_ticker_candidates(asset_code: str, asset_type: str) -> list:
    """Returns the possible Yahoo Finance symbols for the code the user entered."""
    code = asset_code.strip().upper()
    candidates = []

    if asset_type == "Hisse":
        if not code.endswith(".IS") and "." not in code:
            candidates.append(f"{code}.IS")
            candidates.append(code)         # Sonra Amerikan vb.
        else:
            candidates.append(code)

    elif asset_type == "Altın":
        if code in ["ALTIN", "GOLD", "GRAM", "XAU", "GLD"]:
            candidates.extend(["GC=F", "XAUUSD=X"])
        else:
            candidates.append(code)

    elif asset_type == "Döviz":
        if len(code) == 3:
            candidates.extend([f"{code}TRY=X", f"{code}USD=X"])
        if not code.endswith("=X"):
            candidates.append(f"{code}=X")
        candidates.append(code)

    elif asset_type in ["Kripto", "Crypto"]:
        if "-" not in code:
            candidates.append(f"{code}-USD")
        candidates.append(code)

    else:
        candidates.append(code)

    return candidates


def _fetch_gold_gram_price_try() -> float | None:
    """Returns the current gram-gold (GC=F) price in lira; cached for 5
    minutes. Derived gold types such as quarter/half/full/ounce multiply this
    base price by GOLD_TYPE_MULTIPLIERS (see fetch_current_price).
    """
    now = time.time()
    if _gold_gram_cache["price"] is not None and (now - _gold_gram_cache["time"]) < _GOLD_GRAM_CACHE_TTL:
        return _gold_gram_cache["price"]

    price = fetch_current_price("GC=F", "Altın")
    if price is not None:
        _gold_gram_cache["price"] = price
        _gold_gram_cache["time"] = now
        return price
    return _gold_gram_cache["price"]


def fetch_current_price(asset_code: str, asset_type: str) -> float | None:
    """Returns the current closing/spot price for the given symbol, in lira.

    It tries the alternative symbols. For 'Altın' and 'Kripto' the raw price
    arriving from yfinance in USD is converted to lira by _normalize_to_try
    (see the module docstring). Internal symbols such as
    GOLD-ONS/GOLD-CEYREK/GOLD-YARIM/GOLD-TAM have no real yfinance equivalent;
    for those the gram-gold price is fetched and scaled by the standard market
    multiplier. Returns None on error.
    """
    code = (asset_code or "").strip().upper()
    if asset_type == "Altın" and code in GOLD_TYPE_MULTIPLIERS:
        gram_price = _fetch_gold_gram_price_try()
        if gram_price is None:
            return None
        return gram_price * GOLD_TYPE_MULTIPLIERS[code]

    import math
    import yfinance as yf
    import logging


    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    logging.getLogger("requests_cache").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)

    candidates = get_ticker_candidates(asset_code, asset_type)

    for ticker_sym in candidates:
        try:
            ticker = yf.Ticker(ticker_sym)
            hist = ticker.history(period="5d")
            if not hist.empty:
                price = float(hist["Close"].dropna().iloc[-1])
                if not math.isnan(price) and not math.isinf(price):
                    if asset_type in ("Altın", "Kripto", "Crypto"):
                        return _normalize_to_try(price, "Altın" if asset_type == "Altın" else "Kripto")
                    return price
        except Exception as exc:


            _log().debug(
                "%s için '%s' adayı fiyat vermedi: %r",
                asset_code, ticker_sym, exc)

    return None


_BIST_SYMBOL_OVERRIDES = {"USDTR": "USDTRY=X"}


def fetch_bist100_prices(codes: list, callback) -> None:
    """Fetches the prices of the BIST share list in a single batch request, on
    a background thread (Yahoo Finance BIST data, delayed by about 15
    minutes). On completion callback({code: price}) is called; codes that
    could not be fetched are absent from the dictionary.
    """
    import threading

    def _worker():
        import math
        import logging
        import yfinance as yf

        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)

        tickers = {
            code: _BIST_SYMBOL_OVERRIDES.get(code, f"{code}.IS")
            for code in codes
        }
        prices = {}
        try:
            data = yf.download(
                list(tickers.values()),
                period="1d",
                progress=False,
                threads=True,
            )
            close = data["Close"].iloc[-1]
            for code, sym in tickers.items():
                try:
                    price = float(close[sym])
                    if not math.isnan(price) and not math.isinf(price):
                        prices[code] = price
                except (KeyError, IndexError, TypeError, ValueError):


                    pass
        except Exception as e:
            _log().error("BIST100 fiyat çekme hatası: %s", e, exc_info=True)
        callback(prices)

    threading.Thread(target=_worker, daemon=True).start()


# ─── K/Z hesaplama ────────────────────────────────────────────────────────────

def calculate_pnl(current_price: float, purchase_price: float, quantity: float) -> dict:
    """Computes the profit/loss information.

    Return value::
        {
            'pnl_amount':  float,   # net P/L in lira, (current - purchase) * qty
            'pnl_pct':     float,   # P/L as a percentage
            'total_value': float,   # current portfolio value
            'total_cost':  float,   # purchase cost
            'signal':      str      # 'profit' | 'loss' | 'breakeven' | 'error'
        }

    THE ARITHMETIC IS IN DECIMAL, THE OUTER CONTRACT IS FLOAT. Inputs are taken
    with `Decimal(str(x))`, the four operations happen in Decimal, and ONLY on
    return are they rounded to the kurus/percentage and dropped to float -- the
    UI and cache are written against float.

    Inputs are NOT rounded BEFORE the arithmetic. Had they been, a unit price
    of 0.045 would have dropped to 0.04 (and 1e-8 for a crypto quantity would
    have been zeroed entirely); precision is truncated only in the result,
    according to the `FinancialPrecision` policy.

    Why it changed: the four operations were done in binary floating point with
    `round()` applied at the end. `round()` uses the same ROUND_HALF_EVEN as
    the policy -- the difference was not in the mode but in the INPUT: because
    0.045 x 15 is 0.6749999999999999 in binary representation the result came
    out as 0.67, whereas with the numbers the user entered the exact result is
    0.675, that is 0.68. The kurus was being lost to representation error.
    """
    try:
        current = decimal_from(current_price)
        purchase = decimal_from(purchase_price)
        units = decimal_from(quantity)
    except (ValueError, TypeError):


        return {
            "pnl_amount": None, "pnl_pct": None,
            "total_value": None, "total_cost": None,
            "signal": "error",
        }

    total_cost = purchase * units
    total_value = current * units
    pnl_amount = total_value - total_cost
    pnl_ratio = (
        ((current - purchase) / purchase) * 100 if purchase > 0 else Decimal("0")
    )


    if pnl_ratio > 0:
        signal = "profit"
    elif pnl_ratio < 0:
        signal = "loss"
    else:
        signal = "breakeven"

    return {
        "pnl_amount":  float(fiat(pnl_amount)),
        "pnl_pct":     float(percentage(pnl_ratio)),
        "total_value": float(fiat(total_value)),
        "total_cost":  float(fiat(total_cost)),
        "signal":      signal,
    }


PNL_COLORS = {
    "profit":    [0.08, 0.86, 0.29, 1],
    "loss":      [0.95, 0.22, 0.22, 1],
    "breakeven": [0.99, 0.86, 0.02, 1],
    "pending":   [0.65, 0.65, 0.65, 1],   # gri (veri bekleniyor)
    "error":     [0.9, 0.2, 0.2, 1],
}


def get_pnl_color(signal: str) -> list:
    return PNL_COLORS.get(signal, PNL_COLORS["pending"])


def _read_cached_portfolio(assets, allow_stale=False):
    """Return a complete cached portfolio when IDs/positions still match."""
    import json
    from database.db import get_connection

    if not assets:
        return []
    conn = get_connection()
    try:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {_PORTFOLIO_CACHE_TABLE} (
            asset_id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        rows = conn.execute(
            f"SELECT asset_id, payload, updated_at FROM {_PORTFOLIO_CACHE_TABLE}"
        ).fetchall()
        conn.commit()
    finally:
        conn.close()
    by_id = {int(row["asset_id"]): row for row in rows}
    now = int(time.time())
    cached = []
    for asset in assets:
        row = by_id.get(int(asset["id"]))
        if row is None or (not allow_stale and now - int(row["updated_at"]) > _PORTFOLIO_CACHE_TTL):
            return None
        try:
            entry = json.loads(row["payload"])
        except (TypeError, ValueError):
            return None
        if (float(entry.get("quantity", -1)) != float(asset.get("quantity", 0))
                or float(entry.get("purchase_price", -1)) != float(asset.get("purchase_price", 0))):
            return None
        cached.append(entry)
    return cached


def _store_cached_portfolio(enriched):
    import json
    from database.db import get_connection

    if not enriched:
        return
    conn = get_connection()
    try:
        conn.execute(f"""CREATE TABLE IF NOT EXISTS {_PORTFOLIO_CACHE_TABLE} (
            asset_id INTEGER PRIMARY KEY, payload TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )""")
        now = int(time.time())
        conn.executemany(
            f"""INSERT INTO {_PORTFOLIO_CACHE_TABLE}(asset_id, payload, updated_at)
                VALUES (?, ?, ?) ON CONFLICT(asset_id) DO UPDATE SET
                payload=excluded.payload, updated_at=excluded.updated_at""",
            [(int(item["id"]), json.dumps(item, ensure_ascii=False), now)
             for item in enriched],
        )
        conn.commit()
    finally:
        conn.close()


def fetch_portfolio_with_prices(assets: list, callback, item_callback=None,
                                cache_callback=None, force_refresh=False) -> None:
    """Fetches the live prices of every asset in a SINGLE batch yfinance
    request, on a background thread (see the same batch-download pattern in
    fetch_bist100_prices). The previous version made a separate, sequential
    yfinance call per asset; on a portfolio of 12 or more assets that froze
    the application for tens of seconds to a few minutes.

    Internal gold symbols such as GOLD-ONS/GOLD-CEYREK/GOLD-YARIM/GOLD-TAM
    have no real yfinance equivalent; they are excluded from the batch request
    and derived when needed from a one-off GC=F (gram gold) price via a
    multiplier (see GOLD_TYPE_MULTIPLIERS).

    On completion callback(enriched_assets) is called. Each element contains
    (the original asset dict plus extra fields):
        current_price, pnl_amount, pnl_pct, total_value, total_cost, signal
    """
    # Parent/UI process: cache-first, then perform all yfinance/pandas work in
    # a separate interpreter. The child re-enters this function with the env
    # flag and uses the existing local worker implementation below.
    import os
    if not os.environ.get("HELYSOFER_ASSET_PRICE_CHILD"):
        def _isolated_worker():
            fresh = None if force_refresh else _read_cached_portfolio(assets)
            if fresh is not None:
                callback(fresh)
                return
            stale = _read_cached_portfolio(assets, allow_stale=True)
            if stale and cache_callback is not None:
                cache_callback(stale)

            import json
            import subprocess
            import sys
            import tempfile
            fd, output_path = tempfile.mkstemp(prefix="helysofer_prices_", suffix=".json")
            os.close(fd)
            try:
                env = dict(os.environ)
                env["HELYSOFER_ASSET_PRICE_CHILD"] = "1"


                project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                proc = subprocess.run(
                    [sys.executable, "-m", "services.asset_price_worker", output_path],
                    # Asset kinds carry non-ASCII letters. Both ends name the
                    # encoding: left to the locale, parent and child can
                    # disagree and the child then rejects the whole request.
                    input=json.dumps(assets, ensure_ascii=False), text=True,
                    encoding="utf-8", errors="replace",
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    timeout=70, check=False, env=env, cwd=project_root,
                )


                if proc.returncode != 0:
                    _log().error(
                        "Fiyat worker'ı hata kodu %s ile döndü: %s",
                        proc.returncode,
                        (proc.stderr or "").strip()[:500],
                    )
                elif proc.stderr and proc.stderr.strip():
                    _log().warning(
                        "Fiyat worker uyarısı: %s",
                        proc.stderr.strip()[:500],
                    )
                try:
                    with open(output_path, "r", encoding="utf-8") as stream:
                        enriched = json.load(stream)
                except (OSError, ValueError):
                    enriched = stale or []
                if enriched:
                    _store_cached_portfolio(enriched)
                callback(enriched)


            except Exception as exc:
                _log().error("İzole fiyat worker hatası: %s", exc, exc_info=True)
                callback(stale or [])
            finally:
                try:
                    os.unlink(output_path)
                except OSError:
                    pass

        threading.Thread(target=_isolated_worker, daemon=True).start()
        return

    def _error_entries():
        result = []
        for asset in assets:
            entry = dict(asset)
            entry.update({
                "current_price": None, "pnl_amount": None, "pnl_pct": None,
                "total_value": None, "total_cost": None, "signal": "error",
            })
            result.append(entry)
        return result

    def _worker_impl():
        import math
        import logging
        import yfinance as yf

        logging.getLogger("yfinance").setLevel(logging.CRITICAL)
        logging.getLogger("requests_cache").setLevel(logging.CRITICAL)
        logging.getLogger("urllib3").setLevel(logging.CRITICAL)


        ticker_by_id: dict[int, str | None] = {}
        needs_gold_gram = False
        for asset in assets:
            code = (asset["asset_code"] or "").strip().upper()
            a_type = asset["asset_type"]
            if a_type == "Altın" and code in GOLD_TYPE_MULTIPLIERS:
                ticker_by_id[asset["id"]] = None
                needs_gold_gram = True
            else:
                candidates = get_ticker_candidates(asset["asset_code"], a_type)
                ticker_by_id[asset["id"]] = candidates[0] if candidates else None

        unique_tickers = {t for t in ticker_by_id.values() if t}
        if needs_gold_gram:
            unique_tickers.add("GC=F")

        def _last_close(close_obj, sym):
            """Fetches the symbol's last valid close from the yf.download output.

            yfinance 1.4.x returns MultiIndex columns even for a SINGLE symbol
            (('Close','THYAO.IS')), so hist['Close'] may be a DataFrame rather
            than a Series -- the old code got a TypeError from float(Series)
            and silently dropped the price (the root cause of the whole
            portfolio staying at ₺0.00). Both the plain and the MultiIndex
            forms are handled safely.
            """
            if close_obj is None:
                return None
            series = close_obj[sym] if hasattr(close_obj, "columns") else close_obj
            try:
                valid = series.dropna()
            except AttributeError:
                return None
            if len(valid) == 0:
                return None
            price = float(valid.iloc[-1])
            if math.isnan(price) or math.isinf(price):
                return None
            return price

        raw_prices = {}
        if unique_tickers:
            try:
                if len(unique_tickers) == 1:
                    sym = next(iter(unique_tickers))
                    hist = yf.download(sym, period="5d", progress=False)
                    if not hist.empty:
                        price = _last_close(hist["Close"], sym)
                        if price is not None:
                            raw_prices[sym] = price
                else:
                    data = yf.download(
                        list(unique_tickers),
                        period="5d",
                        progress=False,
                        threads=True,
                    )
                    close_df = data["Close"]
                    for sym in unique_tickers:
                        price = _last_close(close_df, sym)
                        if price is not None:
                            raw_prices[sym] = price


            except Exception as e:
                _log().error("Portföy fiyat çekme hatası: %s", e, exc_info=True)


        gram_gold_try = None
        if "GC=F" in raw_prices:
            gram_gold_try = _normalize_to_try(raw_prices["GC=F"], "Altın")
            if gram_gold_try is not None:
                _gold_gram_cache["price"] = gram_gold_try
                _gold_gram_cache["time"] = time.time()
        elif needs_gold_gram:
            gram_gold_try = _fetch_gold_gram_price_try()

        enriched = []
        for asset in assets:
            code = (asset["asset_code"] or "").strip().upper()
            a_type = asset["asset_type"]
            current_price = None

            if a_type == "Altın" and code in GOLD_TYPE_MULTIPLIERS:
                if gram_gold_try is not None:
                    current_price = gram_gold_try * GOLD_TYPE_MULTIPLIERS[code]
            else:


                asset_ticker = ticker_by_id.get(asset["id"])
                raw = raw_prices.get(asset_ticker) if asset_ticker else None
                if raw is not None:
                    if a_type in ("Altın", "Kripto", "Crypto"):
                        current_price = _normalize_to_try(raw, "Altın" if a_type == "Altın" else "Kripto")
                    else:
                        current_price = raw

            entry = dict(asset)
            if current_price is not None:
                pnl = calculate_pnl(current_price, asset["purchase_price"], asset["quantity"])
                entry.update(pnl)
                entry["current_price"] = current_price
            else:
                entry["current_price"] = None
                entry["pnl_amount"]    = None
                entry["pnl_pct"]       = None
                entry["total_value"]   = None
                entry["total_cost"]    = None
                entry["signal"]        = "error"
            enriched.append(entry)
            if item_callback is not None:
                try:
                    item_callback(entry)
                except Exception:
                    from utils.logging_config import get_logger
                    get_logger().exception("Portföy parça callback hatası")
        callback(enriched)

    def _worker():
        try:
            _worker_impl()
        except Exception as exc:


            _log().error(
                "Portföy fiyatlandırma tamamlanamadı: %s", exc, exc_info=True)
            fallback = _error_entries()
            if item_callback is not None:
                for entry in fallback:
                    try:
                        item_callback(entry)
                    except Exception:


                        pass
            try:
                callback(fallback)
            except Exception:
                from utils.logging_config import get_logger
                get_logger().exception("Portföy final callback hatası")

    threading.Thread(target=_worker, daemon=True).start()


COINGECKO_IDS = {
    "BTC": "bitcoin", "ETH": "ethereum", "ETC": "ethereum-classic",
    "USDT": "tether", "USDC": "usd-coin", "BNB": "binancecoin",
    "XRP": "ripple", "ADA": "cardano", "SOL": "solana", "DOGE": "dogecoin",
    "DOT": "polkadot", "TRX": "tron", "AVAX": "avalanche-2",
    "SHIB": "shiba-inu", "LTC": "litecoin", "LINK": "chainlink",
    "MATIC": "matic-network", "XLM": "stellar", "ATOM": "cosmos",
    "UNI": "uniswap", "XMR": "monero", "BCH": "bitcoin-cash",
    "FIL": "filecoin", "APT": "aptos", "ARB": "arbitrum", "OP": "optimism",
}
_PRICE_TIMEOUT = (3.05, 8.0)
_PRICE_CACHE_TABLE = "asset_price_cache"


_CRYPTO_QUOTE_SUFFIXES = ("-USDTRY", "-USDT", "-USDC", "-BUSD", "-USD", "-TRY", "-EUR")


def _coingecko_id_for(asset_code) -> str | None:
    """'BTC-USD' -> 'bitcoin'. The quote suffix is stripped and the bare symbol
    looked up in the map.

    If the code is already bare ('BTC') it matches directly; for non-crypto
    codes None is returned (the caller falls through to the
    yfinance/currency path).
    """
    base = (asset_code or "").strip().upper()
    if not base:
        return None
    for suffix in _CRYPTO_QUOTE_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return COINGECKO_IDS.get(base)


def _frankfurter_base_for(asset_code) -> str | None:
    """Returns the three-letter code of a currency whose lira value can be
    found through Frankfurter: 'USDTRY=X' -> 'USD', 'EUR' -> 'EUR'. Otherwise
    None.

    Only pairs quoted against TRY (...TRY=X) or bare three-letter codes are
    accepted; pairs against something other than TRY, such as 'GBPUSD=X', are
    left out so they cannot be priced wrongly.
    """
    code = (asset_code or "").strip().upper()
    if len(code) == 3 and code.isalpha():
        return code
    if code.endswith("TRY=X"):
        base = code[: -len("TRY=X")]
        if len(base) == 3 and base.isalpha():
            return base
    return None


def get_active_non_try_assets() -> list:
    """Fetches from SQLite the assets with a positive quantity that are not directly lira."""
    from database.db import SECRET_KEY, get_connection
    from utils.crypto import decrypt

    conn = get_connection()
    try:


        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_active_assets_non_try
                ON active_assets(id DESC)
             WHERE UPPER(TRIM(asset_code)) NOT IN ('TRY', 'TL', 'TRY=X')
        """)
        conn.commit()
        rows = conn.execute("""
            SELECT id, asset_name, asset_code, asset_type, purchase_price, quantity
              FROM active_assets
             WHERE UPPER(TRIM(asset_code)) NOT IN ('TRY', 'TL', 'TRY=X')
             ORDER BY id DESC
        """).fetchall()
    finally:
        conn.close()
    assets = []
    for row in rows:
        try:
            quantity = float(decrypt(row["quantity"], SECRET_KEY))
            purchase_price = float(decrypt(row["purchase_price"], SECRET_KEY))
        except KeyUnavailableError:


            raise
        except (DecryptionError, ValueError, TypeError) as e:
            _log().error(
                "[VERİ BÜTÜNLÜĞÜ] active_assets id=%s çözülemedi: %s",
                row["id"], e)
            continue
        if quantity > 0:
            assets.append({
                "id": row["id"], "asset_name": row["asset_name"],
                "asset_code": row["asset_code"], "asset_type": row["asset_type"],
                "purchase_price": purchase_price, "quantity": quantity,
            })
    return assets


def _ensure_price_cache(conn) -> None:
    from database.models import ASSET_PRICE_CACHE_SCHEMA
    conn.execute(ASSET_PRICE_CACHE_SCHEMA)
    conn.commit()


def _read_cached_prices(symbols: set[str]) -> dict[str, float]:
    if not symbols:
        return {}
    from database.db import get_connection
    conn = get_connection()
    try:
        _ensure_price_cache(conn)
        placeholders = ",".join("?" for _ in symbols)
        rows = conn.execute(
            f"SELECT symbol, price FROM {_PRICE_CACHE_TABLE} WHERE symbol IN ({placeholders})",
            tuple(symbols),
        ).fetchall()
        return {row["symbol"]: float(row["price"]) for row in rows}
    finally:
        conn.close()


def _store_prices(prices: dict[str, float]) -> None:
    if not prices:
        return
    from database.db import get_connection
    conn = get_connection()
    try:
        _ensure_price_cache(conn)
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Istanbul")).isoformat()
        conn.executemany(
            f"""INSERT INTO {_PRICE_CACHE_TABLE}
                    (symbol, price, asset_type, updated_at)
                VALUES (?, ?, 'UNKNOWN', ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    price=excluded.price, updated_at=excluded.updated_at""",
            [(symbol, price, now) for symbol, price in prices.items()],
        )
        conn.commit()
    finally:
        conn.close()


def _fetch_live_try_prices(assets: list[dict]) -> dict[str, float]:
    """Fetches lira prices through CoinGecko (crypto) and Frankfurter (currency).

    The returned dictionary is keyed by the asset's full code AS STORED (for
    example 'BTC-USD', 'USDTRY=X'), so the caller
    `fetch_active_non_try_total` can match each asset by its own code and
    multiply by the quantity. Neither service requires an API key. If both are
    unreachable and no price at all can be collected, RuntimeError is
    raised.
    """
    import requests
    prices: dict[str, float] = {}
    errors = []


    crypto_ids = {}
    for asset in assets:
        code = (asset.get("asset_code") or "").strip().upper()
        coin_id = _coingecko_id_for(code)
        if coin_id:
            crypto_ids[code] = coin_id
    if crypto_ids:
        try:
            response = requests.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={"ids": ",".join(sorted(set(crypto_ids.values()))), "vs_currencies": "try"},
                timeout=_PRICE_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
            for full_code, coin_id in crypto_ids.items():


                price = finite_positive_price(
                    payload.get(coin_id, {}).get("try"))
                if price is not None:
                    prices[full_code] = price
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(exc)


    fiat_bases = {}
    for asset in assets:
        if asset.get("asset_type") not in ("Döviz", "Forex"):
            continue
        code = (asset.get("asset_code") or "").strip().upper()
        base = _frankfurter_base_for(code)
        if base and base != "TRY":
            fiat_bases[code] = base
    if fiat_bases:
        try:
            response = requests.get(
                "https://api.frankfurter.app/latest",
                params={"from": "TRY", "to": ",".join(sorted(set(fiat_bases.values())))},
                timeout=_PRICE_TIMEOUT,
            )
            response.raise_for_status()
            rates = response.json().get("rates", {})
            for full_code, base in fiat_bases.items():
                rate = finite_positive_price(rates.get(base))
                if rate is not None:
                    inverted = finite_positive_price(1.0 / rate)
                    if inverted is not None:
                        prices[full_code] = inverted
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(exc)

    if errors and not prices:
        raise RuntimeError("Canlı fiyat servislerine ulaşılamadı") from errors[0]
    return prices


def _monetary_output(total: Decimal) -> float:
    """Converts the Decimal total into the float contract the callers expect.

    `float(total)` IS NOT ENOUGH ON ITS OWN, and this was measured: the
    consumer formats the value
    with `f"{value:,.2f}"`, that is, it rounds on a binary float. If
    `Decimal("2.675")` is converted straight to float, that formatting produces
    **2.67** -- the very error we closed by moving to Decimal, returning one
    step later.

    The rounding is therefore done HERE, with `fiat()`, which owns the money
    policy; the conversion to float comes after it. It is a separate helper so
    that both the intermediate (progress) and the final total pass through the
    same function: the two showing the same money is the contract itself.
    """
    return float(fiat(total))


def fetch_active_non_try_total(callback, progress_callback=None) -> None:
    """Computes the non-lira portfolio total in the background, with a dynamic TTL cache.

    This summary path does not wait for a network result: it sums the last
    prices immediately and leaves refreshing the missing/stale symbols to the
    price_service daemon threads.
    """
    def _load_assets():
        try:
            assets = get_active_non_try_assets()
        except (sqlite3.Error, OSError, HelysoferError) as exc:


            _log().exception("TL dışı varlık listesi okunamadı")
            callback({"total": 0.0, "asset_count": 0, "priced_count": 0,
                      "cached_count": 0, "complete": True, "error": str(exc)})
            return

        if not assets:
            callback({"total": 0.0, "asset_count": 0, "priced_count": 0,
                      "cached_count": 0, "complete": True})
            return


        if progress_callback is not None:
            progress_callback({
                "total": 0.0, "asset_count": len(assets), "priced_count": 0,
                "cached_count": 0, "complete": False,
            })

        from services.price_service import (
            fetch_prices_async, get_cached_prices,
        )

        requested = [
            (
                (asset["asset_code"] or "").strip().upper(),
                asset.get("asset_type"),
            )
            for asset in assets
        ]
        prices = get_cached_prices(symbol for symbol, _kind in requested)

        fetch_prices_async(requested, callback=None)


        total = Decimal("0")
        priced_count = 0
        for asset in assets:
            symbol = (asset["asset_code"] or "").strip().upper()
            price = prices.get(symbol)
            if price is None:
                continue
            try:
                value = decimal_from(asset["quantity"]) * decimal_from(price)
            except (ValueError, TypeError):


                _log().warning(
                    "[VERİ BÜTÜNLÜĞÜ] %s toplama alınamadı: miktar=%r fiyat=%r",
                    symbol, asset.get("quantity"), price,
                )
                continue
            priced_count += 1


            total += value
            if progress_callback is not None:
                progress_callback({
                    "total": _monetary_output(total),
                    "asset_count": len(assets),
                    "priced_count": priced_count,
                    "cached_count": priced_count, "complete": False,
                    "asset": asset,
                })
        callback({
            "total": _monetary_output(total), "asset_count": len(assets),
            "priced_count": priced_count, "cached_count": priced_count,
            "complete": True,
        })

    threading.Thread(target=_load_assets, daemon=True).start()
