"""Market-data provider interface, raw snapshot DTO, and error hierarchy.

The DTO uses provider-agnostic domain field names. A concrete provider is
responsible for translating its own wire format into this shape, so no
provider-specific key ever reaches normalization or the scoring engine
(AGENTS.md §2). Every numeric field is ``float | None``: ``None`` means the
provider did not supply the value and it must be recorded as explicit
missing-data (never ``0`` — ADR-003), which ``normalize`` enforces.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime


class ProviderError(Exception):
    """Base class for all provider failures (never leaked to API consumers)."""


class ProviderUnavailable(ProviderError):
    """The provider could not be reached (network error, timeout, 5xx)."""


class RateLimited(ProviderError):
    """The provider rejected the request due to rate limiting (HTTP 429)."""


class MalformedResponse(ProviderError):
    """The provider responded, but the payload was not the expected shape."""


@dataclass(frozen=True)
class RawMarketSnapshot:
    """One provider observation of an asset's market state, provider-agnostic.

    Identity fields (``external_id``, ``symbol``, ``name``) plus optional numeric
    market metrics. ``observed_at`` is the provider's own timestamp for the data
    when available (used for provenance and freshness), else ``None``.
    """

    external_id: str
    symbol: str
    name: str
    observed_at: datetime | None

    price_usd: float | None
    market_cap_usd: float | None
    fully_diluted_valuation_usd: float | None
    total_volume_usd: float | None
    circulating_supply: float | None
    total_supply: float | None
    max_supply: float | None
    price_change_pct_24h: float | None
    price_change_pct_7d: float | None
    price_change_pct_30d: float | None
    market_cap_rank: float | None


class MarketDataProvider(ABC):
    """Interface every market-data source implements.

    Implementations must handle missing/stale data, API failures, rate limits and
    malformed responses (AGENTS.md §13), translating transport/shape problems into
    the ``ProviderError`` hierarchy and absent values into ``None`` fields.
    """

    #: Stable short identifier stored as provenance (e.g. ``"coingecko"``).
    name: str

    @abstractmethod
    def fetch_markets(
        self,
        *,
        ids: Sequence[str] | None = None,
        top_n: int | None = None,
    ) -> list[RawMarketSnapshot]:
        """Return market snapshots for the requested universe.

        Exactly one selection mode is used: an explicit ``ids`` list, or the
        ``top_n`` assets by market capitalization. Raises a ``ProviderError``
        subclass on transport, rate-limit, or shape failures.
        """
        raise NotImplementedError


@dataclass(frozen=True)
class RawFundamentalSnapshot:
    """One provider observation of a protocol's economic fundamentals.

    Identity fields describe the protocol; ``gecko_id`` is the provider-neutral key
    used to join a protocol to an internal asset (never the ambiguous symbol, §13).
    Every numeric field is ``float | None``: ``None`` means the provider did not
    report it and it must be recorded as explicit missing-data (never ``0``,
    ADR-003). Fees, revenue, holders-revenue, and TVL are kept strictly distinct
    (AGENTS.md §9) and must never be derived from one another.
    """

    slug: str
    name: str
    gecko_id: str | None
    symbol: str | None
    category: str | None
    observed_at: datetime | None

    tvl_usd: float | None
    fees_24h_usd: float | None
    fees_7d_usd: float | None
    fees_30d_usd: float | None
    revenue_24h_usd: float | None
    revenue_7d_usd: float | None
    revenue_30d_usd: float | None
    holders_revenue_24h_usd: float | None
    holders_revenue_30d_usd: float | None


class FundamentalDataProvider(ABC):
    """Interface every protocol-fundamentals source implements.

    Same failure contract as ``MarketDataProvider``: transport/shape problems become
    ``ProviderError`` subclasses and absent values become ``None`` fields.
    """

    #: Stable short identifier stored as provenance (e.g. ``"defillama"``).
    name: str

    @abstractmethod
    def fetch_fundamentals(self) -> list[RawFundamentalSnapshot]:
        """Return fundamentals snapshots for the provider's tracked protocols.

        Raises a ``ProviderError`` subclass on transport, rate-limit, or shape
        failures.
        """
        raise NotImplementedError
