"""CoinGecko market-data provider.

Concrete ``MarketDataProvider`` over CoinGecko's ``/coins/markets`` endpoint.
This is the only module that knows CoinGecko's wire field names; everything
downstream sees the provider-agnostic ``RawMarketSnapshot`` (AGENTS.md §2).

Transport is a synchronous ``httpx.Client`` (matches the sync stack chosen in
Sprint 01). An ``httpx.Client`` may be injected for deterministic, offline tests
(via ``httpx.MockTransport``); no live network call is made in the test suite.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import httpx

from alphadex.logging import get_logger
from alphadex.providers.base import (
    MalformedResponse,
    MarketDataProvider,
    ProviderUnavailable,
    RateLimited,
    RawMarketSnapshot,
)

logger = get_logger(__name__)


def _num(value: Any) -> float | None:
    """Coerce a raw value to ``float`` or ``None``.

    Absent, null, or non-numeric values become ``None`` (recorded later as
    explicit missing-data), never ``0`` (ADR-003).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse CoinGecko's ISO-8601 ``last_updated`` (``...Z``) to a datetime."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


class CoinGeckoProvider(MarketDataProvider):
    """Fetches market data from CoinGecko's public/demo API."""

    name = "coingecko"

    def __init__(
        self,
        *,
        base_url: str = "https://api.coingecko.com/api/v3",
        api_key: str | None = None,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        # An injected client (tests) owns its own transport; otherwise we manage one.
        self._client = client
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self._api_key:
            # Demo-tier header; Pro tier uses ``x-cg-pro-api-key``.
            headers["x-cg-demo-api-key"] = self._api_key
        return headers

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def fetch_markets(
        self,
        *,
        ids: Sequence[str] | None = None,
        top_n: int | None = None,
    ) -> list[RawMarketSnapshot]:
        params: dict[str, Any] = {
            "vs_currency": "usd",
            "price_change_percentage": "24h,7d,30d",
            "order": "market_cap_desc",
        }
        if ids:
            params["ids"] = ",".join(ids)
            params["per_page"] = len(list(ids))
        else:
            params["per_page"] = top_n if top_n and top_n > 0 else 50
            params["page"] = 1

        url = f"{self._base_url}/coins/markets"
        try:
            response = self._get_client().get(
                url, params=params, headers=self._headers()
            )
        except httpx.RequestError as exc:
            logger.error("provider_request_failed", provider=self.name, error=str(exc))
            raise ProviderUnavailable(f"CoinGecko request failed: {exc}") from exc

        if response.status_code == 429:
            raise RateLimited("CoinGecko rate limit exceeded (HTTP 429)")
        if response.status_code >= 500:
            raise ProviderUnavailable(
                f"CoinGecko server error (HTTP {response.status_code})"
            )
        if response.status_code >= 400:
            raise MalformedResponse(
                f"CoinGecko rejected the request (HTTP {response.status_code})"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise MalformedResponse("CoinGecko returned invalid JSON") from exc

        if not isinstance(payload, list):
            raise MalformedResponse(
                "CoinGecko response was not a list of market entries"
            )

        snapshots: list[RawMarketSnapshot] = []
        for item in payload:
            snapshots.append(self._to_snapshot(item))
        logger.info("provider_fetch_ok", provider=self.name, count=len(snapshots))
        return snapshots

    def _to_snapshot(self, item: Any) -> RawMarketSnapshot:
        if not isinstance(item, Mapping):
            raise MalformedResponse("CoinGecko market entry was not an object")
        external_id = item.get("id")
        symbol = item.get("symbol")
        name = item.get("name")
        if not external_id or not symbol or not name:
            raise MalformedResponse("CoinGecko market entry missing id/symbol/name")
        return RawMarketSnapshot(
            external_id=str(external_id),
            symbol=str(symbol).upper(),
            name=str(name),
            observed_at=_parse_timestamp(item.get("last_updated")),
            price_usd=_num(item.get("current_price")),
            market_cap_usd=_num(item.get("market_cap")),
            fully_diluted_valuation_usd=_num(item.get("fully_diluted_valuation")),
            total_volume_usd=_num(item.get("total_volume")),
            circulating_supply=_num(item.get("circulating_supply")),
            total_supply=_num(item.get("total_supply")),
            max_supply=_num(item.get("max_supply")),
            price_change_pct_24h=_num(item.get("price_change_percentage_24h")),
            price_change_pct_7d=_num(
                item.get("price_change_percentage_7d_in_currency")
            ),
            price_change_pct_30d=_num(
                item.get("price_change_percentage_30d_in_currency")
            ),
            market_cap_rank=_num(item.get("market_cap_rank")),
        )

    def close(self) -> None:
        """Close the underlying client if this provider created it."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
