"""Data provider adapters.

Business logic depends only on the interfaces defined here (AGENTS.md §2, §13);
concrete providers (e.g. CoinGecko) are swappable without touching normalization,
persistence, or scoring. A provider's wire shape never leaks past its own module.
"""

from __future__ import annotations

from alphadex.providers.base import (
    MalformedResponse,
    MarketDataProvider,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RawMarketSnapshot,
)

__all__ = [
    "MarketDataProvider",
    "RawMarketSnapshot",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "MalformedResponse",
]
