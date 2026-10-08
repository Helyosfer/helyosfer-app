"""Best-effort brand icon service for transaction and subscription names.

A recognised brand name is extracted from the text and the PNG logo is cached
in a separate local directory. Network/HTTP/content errors are never carried
to the caller; the interface carries on with its generic category icon.

"""

import os
import re
import unicodedata

from utils.app_paths import cache_dir


BRAND_ICON_CACHE_DIR = os.path.join(cache_dir(), "brand_icon_cache_v3")


MIN_ACCEPTABLE_ICON_PX = 16


TARGET_ICON_PX = 128


_MISS_TTL_SECONDS = 30 * 24 * 3600


_BRANDS = (
    (("amazon prime", "prime video"), "prime-video", "primevideo.com"),
    (("youtube premium", "youtube music", "youtube"), "youtube", "youtube.com"),
    (("apple music", "apple tv", "icloud", "apple"), "apple", "apple.com"),
    (("disney plus", "disney+"), "disney-plus", "disneyplus.com"),
    (("netflix",), "netflix", "netflix.com"),
    (("spotify",), "spotify", "spotify.com"),
    (("max", "hbo max"), "max", "max.com"),
    (("blutv", "blu tv"), "blutv", "blutv.com"),
    (("exxen",), "exxen", "exxen.com"),
    (("gain",), "gain", "gain.tv"),
    (("mubi",), "mubi", "mubi.com"),
    (("deezer",), "deezer", "deezer.com"),
    (("tod tv", "tod"), "tod", "todtv.com.tr"),
    (("tabii",), "tabii", "tabii.com"),


    (("twitch",), "twitch", "twitch.tv"),
    (("paramount plus", "paramount+"), "paramount-plus", "paramountplus.com"),
    (("peacock",), "peacock", "peacocktv.com"),
    (("crunchyroll",), "crunchyroll", "crunchyroll.com"),


    (("tidal",), "tidal", "tidal.com"),
    (("soundcloud", "soundcloud go"), "soundcloud", "soundcloud.com"),

    # ── Books / audiobooks ──────────────────────────────────────────────
    (("storytel",), "storytel", "storytel.com"),
    (("audible",), "audible", "audible.com"),
    (("kindle unlimited",), "kindle-unlimited", "amazon.com"),
    (("blinkist",), "blinkist", "blinkist.com"),

    # ── Oyun ────────────────────────────────────────────────────────────
    (("playstation plus", "ps plus", "psn"), "playstation-plus", "playstation.com"),
    (("xbox game pass", "game pass", "xbox"), "xbox-game-pass", "xbox.com"),
    (("nintendo switch online", "nintendo online"), "nintendo-online", "nintendo.com"),
    (("ea play",), "ea-play", "ea.com"),
    (("ubisoft+", "ubisoft plus"), "ubisoft-plus", "ubisoft.com"),

    # ── Bulut depolama ──────────────────────────────────────────────────
    (("google one", "google drive"), "google-one", "one.google.com"),
    (("dropbox",), "dropbox", "dropbox.com"),


    (("microsoft 365", "office 365"), "microsoft-365", "microsoft.com"),
    (("adobe creative cloud", "adobe cc", "creative cloud"), "adobe-cc", "adobe.com"),
    (("canva",), "canva", "canva.com"),
    (("notion",), "notion", "notion.so"),
    (("chatgpt", "chat gpt", "openai"), "chatgpt", "openai.com"),
    (("github copilot", "github"), "github", "github.com"),
    (("slack",), "slack", "slack.com"),
    (("zoom",), "zoom", "zoom.us"),
    (("linkedin premium", "linkedin"), "linkedin", "linkedin.com"),
    (("figma",), "figma", "figma.com"),
    (("jetbrains",), "jetbrains", "jetbrains.com"),
    (("1password", "1 password"), "1password", "1password.com"),
    (("lastpass", "last pass"), "lastpass", "lastpass.com"),
    (("claude", "anthropic"), "claude", "claude.ai"),
    (("gemini advanced", "google gemini", "gemini"), "gemini", "gemini.google.com"),

    (("udemy",), "udemy", "udemy.com"),
    (("coursera",), "coursera", "coursera.org"),
    (("duolingo",), "duolingo", "duolingo.com"),
    (("skillshare",), "skillshare", "skillshare.com"),


    (("macfit", "mac fit"), "macfit", "macfit.com"),
    (("club sporium", "clubsporium", "sporium"), "sporium", "clubsporium.com.tr"),
    (("strava",), "strava", "strava.com"),
    (("headspace",), "headspace", "headspace.com"),


    (("patreon",), "patreon", "patreon.com"),
    (("wikipedia", "wikimedia"), "wikipedia", "wikipedia.org"),


    (("proton vpn", "protonvpn"), "proton-vpn", "protonvpn.com"),
    (("proton mail", "protonmail"), "proton-mail", "proton.me"),
    (("proton pass", "protonpass"), "proton-pass", "proton.me"),
    (("proton drive", "protondrive"), "proton-drive", "proton.me"),
    (("proton calendar", "protoncalendar"), "proton-calendar", "proton.me"),
    (
        ("proton unlimited", "proton duo", "proton family",
         "proton visionary", "proton"),
        "proton",
        "proton.me",
    ),


    (
        ("turkcell superonline", "superonline"),
        "superonline",
        "superonline.net",
    ),
    (
        ("türk telekom", "turk telekom", "türktelekom", "turktelekom",
         "ttnet"),
        "turk-telekom",
        "turktelekom.com.tr",
    ),
    (
        ("vodafone türkiye", "vodafone turkey", "vodafone net", "vodafone"),
        "vodafone",
        "vodafone.com.tr",
    ),
    (
        ("turkcell",),
        "turkcell",
        "turkcell.com.tr",
    ),


    (("meta verified", "instagram"), "instagram", "instagram.com"),

    # ── VPN ─────────────────────────────────────────────────────────────
    (("nordvpn", "nord vpn"), "nordvpn", "nordvpn.com"),
    (("expressvpn", "express vpn"), "expressvpn", "expressvpn.com"),


    (("garanti bbva", "garanti bankası", "garanti"), "garanti", "garantibbva.com.tr"),
    (("iş bankası", "is bankasi", "işcep", "iscep", "is bank"), "is-bankasi", "isbank.com.tr"),
    (("yapı kredi", "yapi kredi", "yapıkredi", "yapikredi"), "yapi-kredi", "yapikredi.com.tr"),
    (("ziraat bankası", "ziraat bankasi", "ziraat"), "ziraat", "ziraatbank.com.tr"),
    (("akbank", "axess"), "akbank", "akbank.com"),
    (("vakıfbank", "vakifbank", "vakıf bank", "vakif bank"), "vakifbank", "vakifbank.com.tr"),
    (("halkbank", "halk bank", "halk bankası"), "halkbank", "halkbank.com.tr"),
    (("enpara.com", "enpara"), "enpara", "enpara.com"),
    (("qnb finansbank", "finansbank", "qnb"), "qnb", "qnbfinansbank.com"),
    (("teb", "türk ekonomi bankası", "cepteteb"), "teb", "teb.com.tr"),
    (("denizbank", "deniz bank"), "denizbank", "denizbank.com"),
    (("kuveyt türk", "kuveyttürk", "kuveyt turk"), "kuveytturk", "kuveytturk.com.tr"),
    (("türkiye finans", "turkiye finans"), "turkiye-finans", "turkiyefinans.com.tr"),
    (("albaraka", "albaraka türk"), "albaraka", "albarakaturk.com.tr"),
    (("papara",), "papara", "papara.com"),
    (("ininal", "ininal kart"), "ininal", "ininal.com"),
    (("tosla",), "tosla", "tosla.com"),
    (("paycell",), "paycell", "paycell.com.tr"),
    (("nays",), "nays", "naysapp.com.tr"),
    (("pokus",), "pokus", "pokus.com.tr"),
    (("ozan", "ozan superapp"), "ozan", "ozan.com"),


    (("google",), "google", "google.com"),
    (("amazon",), "amazon", "amazon.com"),
)


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or "").casefold())
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9+]+", " ", ascii_text).split())


_NORMALIZED_BRANDS = tuple(
    (
        tuple(f" {_normalize(alias)} " for alias in aliases),
        cache_key,
        domain,
    )
    for aliases, cache_key, domain in _BRANDS
)


def icon_source_urls(domain: str) -> tuple[str, ...]:
    """Returns the provider candidates for `domain`, in order.

    WHY ONE PROVIDER IS NOT ENOUGH (measured): no provider is best
    for every brand. The largest edge returned for the same domains:

        domain             google sz=256   icon.horse
        claude.ai          248             48
        openai.com         180             256
        google.com         144             32

    Tying to a single provider means a poor icon for the brands that provider
    is weak on -- which is why the Clearbit -> Google Favicon -> icon.horse
    moves never fully solved each other. Instead the candidates are tried in
    order and the first result exceeding `TARGET_ICON_PX` wins; if none does,
    the largest is chosen (see `fetch_and_cache_brand_icon`).
    """
    return (
        f"https://www.google.com/s2/favicons?domain={domain}&sz=256",
        f"https://icon.horse/icon/{domain}",
        f"https://unavatar.io/{domain}",
    )


def _classify_domain(text: str):
    """Returns ``(cache_key, domain)``; ``(None, None)`` when there is no match."""
    normalized = _normalize(text)
    if not normalized:
        return None, None
    padded = f" {normalized} "
    for aliases, cache_key, domain in _NORMALIZED_BRANDS:
        if any(alias in padded for alias in aliases):
            return cache_key, domain
    return None, None


def classify_brand(text: str):
    """Returns ``(cache_key, png_url)`` for the text; Nones when there is no match.

    The returned URL is the **primary** provider. The download path is not
    tied to a single URL; it tries every candidate via `icon_source_urls`.
    """
    cache_key, domain = _classify_domain(text)
    if not cache_key:
        return None, None
    return cache_key, icon_source_urls(domain)[0]


def resolve_cached_brand_icon_path(text: str) -> str | None:
    """Checks the local cache only; makes no network call."""
    cache_key, _ = classify_brand(text)
    if not cache_key:
        return None
    path = os.path.join(BRAND_ICON_CACHE_DIR, f"{cache_key}.png")
    return path if os.path.exists(path) else None


def _miss_path(cache_key: str) -> str:
    return os.path.join(BRAND_ICON_CACHE_DIR, f"{cache_key}.miss")


def _miss_is_fresh(cache_key: str) -> bool:
    """Was a "no suitable logo" decision made recently for this brand?"""
    import time

    try:
        age = time.time() - os.path.getmtime(_miss_path(cache_key))
    except OSError:
        return False
    return age < _MISS_TTL_SECONDS


def _record_miss(cache_key: str) -> None:
    """Marks a failed lookup; on error it gives up silently (we only lose the
    next attempt's early exit, the behaviour does not break).
    """
    try:
        os.makedirs(BRAND_ICON_CACHE_DIR, exist_ok=True)
        with open(_miss_path(cache_key), "wb"):
            pass
    except OSError:
        pass


def _decode_largest_frame(payload: bytes):
    """Decodes the bytes and returns the LARGEST frame as RGBA; None if it cannot.

    Content-Type is NOT TRUSTED -- the content is verified by actually
    decoding it. Two concrete reasons (both measured in the field):

      * Providers can return an ICO for a `.png` request (icon.horse ->
        claude.ai/turkcell.com.tr). The old code wrote the raw bytes to disk
        under the name `{key}.png`: the file was an ICO named as a PNG.
        Because Pillow sniffs the content it happened to open on the desktop,
        but it was open to silent breakage in any environment that picks a
        loader by extension (SDL2_image in the packaged Windows build).
      * An ICO can have multiple frames; if a 16x16 frame sits beside a
        256x256 one, the large one has to be chosen.
    """
    from io import BytesIO

    from PIL import Image

    image = Image.open(BytesIO(payload))
    if getattr(image, "format", None) == "ICO":
        try:


            largest = max(image.ico.sizes())  # type: ignore[attr-defined]
            image = image.ico.getimage(largest)  # type: ignore[attr-defined]
        except (AttributeError, KeyError, ValueError, OSError):


            pass
    return image.convert("RGBA")


def fetch_and_cache_brand_icon(text: str) -> bool:
    """Downloads a recognised brand's logo and caches it as a REAL PNG.

    The candidates are tried in order and it stops at the first result
    exceeding `TARGET_ICON_PX`, otherwise the largest is chosen. If the result
    is below `MIN_ACCEPTABLE_ICON_PX`, NOTHING is written and False is
    returned -- the interface carries on using its own vector icon for that
    brand (rather than showing a blurry 16x16 smudge). Network/HTTP/decode
    errors are never carried to the caller.
    """
    cache_key, domain = _classify_domain(text)
    if not cache_key or not domain:
        return False

    destination = os.path.join(BRAND_ICON_CACHE_DIR, f"{cache_key}.png")
    if os.path.exists(destination):
        return True
    if _miss_is_fresh(cache_key):
        return False

    best = None
    for url in icon_source_urls(domain):
        try:
            import requests

            response = requests.get(url, timeout=4)
            if response.status_code != 200 or not response.content:
                continue
            candidate = _decode_largest_frame(response.content)
        except (OSError, ValueError):


            continue
        if best is None or candidate.size[0] > best.size[0]:
            best = candidate
        if best.size[0] >= TARGET_ICON_PX:
            break

    if best is None or best.size[0] < MIN_ACCEPTABLE_ICON_PX:
        _record_miss(cache_key)
        return False

    if best.size[0] < TARGET_ICON_PX:


        try:
            from PIL import Image


            best = best.resize(
                (TARGET_ICON_PX, TARGET_ICON_PX), Image.Resampling.LANCZOS)
        except (OSError, ValueError, AttributeError):
            pass

    try:
        os.makedirs(BRAND_ICON_CACHE_DIR, exist_ok=True)
        best.save(destination, format="PNG")
        return True
    except (OSError, ValueError):
        return False
