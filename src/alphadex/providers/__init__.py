"""Data provider adapters.

Business logic depends only on the interfaces defined here (AGENTS.md §2, §13);
concrete providers (e.g. CoinGecko) are swappable without touching normalization,
persistence, or scoring. A provider's wire shape never leaks past its own module.
"""

from __future__ import annotations

from alphadex.providers.base import (
    FundamentalDataProvider,
    MalformedResponse,
    MarketDataProvider,
    ProviderError,
    ProviderUnavailable,
    RateLimited,
    RawFundamentalSnapshot,
    RawMarketSnapshot,
)

__all__ = [
    "MarketDataProvider",
    "RawMarketSnapshot",
    "FundamentalDataProvider",
    "RawFundamentalSnapshot",
    "ProviderError",
    "ProviderUnavailable",
    "RateLimited",
    "MalformedResponse",
]
