"""Logo Service -- fetches remote logo/flag/icon images for the Crypto,
Currency and Gold entries in the asset-history list and caches them to local
disk.

Only Crypto, Currency and Gold are handled.
No logo is looked up for Bond/Other either, where the generic coloured
icon fallback is enough.

Network access is ALWAYS best-effort: none of a timeout, DNS failure, 404 or
corrupt content raises an exception -- fetch_and_cache_logo silently returns
False and the caller falls back to the generic icon.

"""
import os

LOGO_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo_cache"
)


_CRYPTO_SYMBOLS = {"BTC", "ETH", "USDT", "BNB", "SOL", "XRP", "DOGE", "ADA", "AVAX", "DOT"}


_FOREX_COUNTRY = {
    "USD": "us", "EUR": "eu", "GBP": "gb", "JPY": "jp",
    "CHF": "ch", "CAD": "ca", "AUD": "au",
}


_GOLD_KEYWORDS = ("GC=F", "XAU", "ALTIN", "GOLD")

_GOLD_LOGO_URL = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1fa99.png"


def _classify(code: str):
    """Returns (cache_key, remote_url) for a raw code (for example 'BTC-USD',
    'USDTRY=X', 'GC=F'). Returns (None, None) for unrecognised or unsupported
    codes -- in which case no network call is attempted at all.
    """
    c = (code or "").strip().upper()

    if c.endswith("-USD"):
        sym = c.split("-")[0]
        if sym in _CRYPTO_SYMBOLS:
            return sym, f"https://assets.coincap.io/assets/icons/{sym.lower()}@2x.png"

    elif c.endswith("=X") and len(c) >= 5:
        base = c[:3]
        if base in _FOREX_COUNTRY:
            return base, f"https://flagcdn.com/w80/{_FOREX_COUNTRY[base]}.png"

    elif any(keyword in c for keyword in _GOLD_KEYWORDS):
        return "XAU", _GOLD_LOGO_URL

    return None, None


def resolve_remote_logo_url(code: str) -> str | None:
    """Returns, for a raw code and WITH NO NETWORK CALL, the remote logo URL
    that can be handed straight to an AsyncImage/FitImage `source`; None for
    unrecognised codes. The widget's own async loader makes the actual network
    request and this function only produces the URL -- it is used for the
    instant preview in the Add Asset flow (it does not write to the persistent
    cache, see fetch_and_cache_logo).
    """
    _, url = _classify(code)
    return url


def resolve_cached_logo_path(code: str) -> str | None:
    """Checks local disk only (NO NETWORK CALL) -- safe to call from the UI
    thread. Returns the path of a logo that has been downloaded successfully
    before, or None.
    """
    cache_key, _ = _classify(code)
    if not cache_key:
        return None
    path = os.path.join(LOGO_CACHE_DIR, f"{cache_key}.png")
    return path if os.path.exists(path) else None


def fetch_and_cache_logo(code: str) -> bool:
    """Must be called from a background thread -- it makes a blocking network
    request. Downloads the logo and writes it to the cache. Silently returns
    False if the code is unrecognised, the network is unreachable, the request
    times out, or the returned content is not an image; it raises an exception
    under no circumstance.
    """
    cache_key, url = _classify(code)
    if not cache_key or not url:
        return False

    dest = os.path.join(LOGO_CACHE_DIR, f"{cache_key}.png")
    if os.path.exists(dest):
        return True

    try:
        import requests
        resp = requests.get(url, timeout=4)
        content_type = resp.headers.get("Content-Type", "")
        if resp.status_code == 200 and content_type.startswith("image/") and resp.content:
            os.makedirs(LOGO_CACHE_DIR, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(resp.content)
            return True
    except Exception:
        from utils.logging_config import get_logger
        get_logger().exception("Logo indirilemedi")
    return False
