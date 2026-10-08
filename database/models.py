"""Database schema models.

The project uses no ORM, so the models are kept as lightweight dataclasses
carrying the SQLite table contract. The actual table setup and migration
live in init_db.

"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


@dataclass(frozen=True)
class AssetPriceCache:
    """The last known price of an API symbol, normalised to Turkish lira."""

    symbol: str
    price: float
    asset_type: str
    updated_at: datetime


    source: str = "Yahoo Finance"


class PriceFreshness(str, Enum):
    CURRENT = "current"
    DELAYED = "delayed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class AssetPriceStatus:
    symbol: str
    price: Decimal | None
    source: str
    updated_at: datetime | None
    cache_age_seconds: int | None
    freshness: PriceFreshness


ASSET_PRICE_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS asset_price_cache (
    symbol TEXT PRIMARY KEY,
    price REAL NOT NULL,
    asset_type TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    -- NULL olabilir: sütun eklenmeden önceki satırlar. Okuma tarafı bunu
    -- "Yahoo Finance"a çözer (o dönemde tek sağlayıcı oydu).
    source TEXT
)
"""
