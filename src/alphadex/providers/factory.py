"""Provider factory — selects a concrete provider from configuration.

Keeps the choice of provider in one place (config-driven, AGENTS.md §2), so
callers depend only on the ``MarketDataProvider`` interface.
"""

from __future__ import annotations

from alphadex.config import Settings
from alphadex.providers.base import FundamentalDataProvider, MarketDataProvider
from alphadex.providers.coingecko import CoinGeckoProvider
from alphadex.providers.defillama import DefiLlamaProvider


def build_market_data_provider(settings: Settings) -> MarketDataProvider:
    """Instantiate the configured market-data provider."""
    provider = settings.market_data_provider.lower()
    if provider == "coingecko":
        return CoinGeckoProvider(
            base_url=settings.coingecko_base_url,
            api_key=settings.coingecko_api_key,
            timeout=settings.provider_timeout_seconds,
        )
    raise ValueError(f"Unknown market data provider: {settings.market_data_provider!r}")


def build_fundamental_data_provider(settings: Settings) -> FundamentalDataProvider:
    """Instantiate the configured fundamental-data provider."""
    provider = settings.fundamental_data_provider.lower()
    if provider == "defillama":
        return DefiLlamaProvider(
            base_url=settings.defillama_base_url,
            api_key=settings.defillama_api_key,
            timeout=settings.provider_timeout_seconds,
        )
    raise ValueError(
        f"Unknown fundamental data provider: {settings.fundamental_data_provider!r}"
    )
