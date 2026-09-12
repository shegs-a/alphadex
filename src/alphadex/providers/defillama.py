"""DefiLlama fundamentals provider.

Concrete ``FundamentalDataProvider`` over DefiLlama's public API. This is the only
module that knows DefiLlama's wire field names; everything downstream sees the
provider-agnostic ``RawFundamentalSnapshot`` (AGENTS.md §2).

Fundamentals are assembled from three cheap, broad calls (AGENTS.md §9):
- ``/protocols``            → TVL + identity (slug, gecko_id, symbol, category)
- ``/overview/fees``        → fees (total24h/7d/30d) per protocol slug
- ``/overview/fees?dataType=dailyRevenue`` → revenue per protocol slug
Holders-revenue is fetched best-effort (a failure is logged, not fatal).

Fees, revenue, holders-revenue, and TVL are separate metrics and are never derived
from one another (AGENTS.md §9).

Phase-1 identity rule: snapshots are keyed by ``gecko_id`` (the provider-neutral
join key to an internal asset). When several protocols share one ``gecko_id`` in a
run, the one with the largest TVL is kept as the representative to avoid
double-counting; protocols without a ``gecko_id`` are dropped (they cannot be
matched this phase).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from alphadex.logging import get_logger
from alphadex.providers.base import (
    FundamentalDataProvider,
    MalformedResponse,
    ProviderUnavailable,
    RateLimited,
    RawFundamentalSnapshot,
)

logger = get_logger(__name__)


def _num(value: Any) -> float | None:
    """Coerce a raw value to ``float`` or ``None`` (never ``0`` for missing)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class DefiLlamaProvider(FundamentalDataProvider):
    """Fetches protocol fundamentals (fees, revenue, TVL) from DefiLlama."""

    name = "defillama"

    def __init__(
        self,
        *,
        base_url: str = "https://api.llama.fi",
        api_key: str | None = None,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    def _headers(self) -> dict[str, str]:
        headers = {"accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _get_client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout)
        return self._client

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = self._get_client().get(
                url, params=params, headers=self._headers()
            )
        except httpx.RequestError as exc:
            logger.error("provider_request_failed", provider=self.name, error=str(exc))
            raise ProviderUnavailable(f"DefiLlama request failed: {exc}") from exc

        if response.status_code == 429:
            raise RateLimited("DefiLlama rate limit exceeded (HTTP 429)")
        if response.status_code >= 500:
            raise ProviderUnavailable(
                f"DefiLlama server error (HTTP {response.status_code})"
            )
        if response.status_code >= 400:
            raise MalformedResponse(
                f"DefiLlama rejected the request (HTTP {response.status_code})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise MalformedResponse("DefiLlama returned invalid JSON") from exc

    def _fetch_overview_by_slug(self, data_type: str | None) -> dict[str, Any]:
        """Return ``slug → entry`` from an ``/overview/fees`` variant."""
        params: dict[str, Any] = {
            "excludeTotalDataChart": "true",
            "excludeTotalDataChartBreakdown": "true",
        }
        if data_type:
            params["dataType"] = data_type
        payload = self._get("/overview/fees", params)
        if not isinstance(payload, Mapping):
            raise MalformedResponse("DefiLlama fees overview was not an object")
        protocols = payload.get("protocols")
        if not isinstance(protocols, list):
            raise MalformedResponse("DefiLlama fees overview missing 'protocols'")
        by_slug: dict[str, Any] = {}
        for entry in protocols:
            if isinstance(entry, Mapping):
                slug = entry.get("slug")
                if slug:
                    by_slug[str(slug)] = entry
        return by_slug

    def fetch_fundamentals(self) -> list[RawFundamentalSnapshot]:
        protocols = self._get("/protocols")
        if not isinstance(protocols, list):
            raise MalformedResponse("DefiLlama /protocols was not a list")

        fees = self._fetch_overview_by_slug(None)
        revenue = self._fetch_overview_by_slug("dailyRevenue")
        # Holders revenue is best-effort: a failure is logged, not fatal (§8).
        try:
            holders = self._fetch_overview_by_slug("dailyHoldersRevenue")
        except Exception as exc:  # noqa: BLE001 - degrade gracefully, but observably
            logger.warning(
                "holders_revenue_unavailable", provider=self.name, error=str(exc)
            )
            holders = {}

        # Assemble one candidate per protocol slug that carries a gecko_id.
        candidates: list[RawFundamentalSnapshot] = []
        for proto in protocols:
            if not isinstance(proto, Mapping):
                continue
            gecko_id = proto.get("gecko_id")
            slug = proto.get("slug")
            name = proto.get("name")
            if not gecko_id or not slug or not name:
                continue
            fee = fees.get(str(slug), {})
            rev = revenue.get(str(slug), {})
            hol = holders.get(str(slug), {})
            candidates.append(
                RawFundamentalSnapshot(
                    slug=str(slug),
                    name=str(name),
                    gecko_id=str(gecko_id),
                    symbol=str(proto["symbol"]).upper()
                    if proto.get("symbol")
                    else None,
                    category=str(proto["category"]) if proto.get("category") else None,
                    observed_at=None,
                    tvl_usd=_num(proto.get("tvl")),
                    fees_24h_usd=_num(fee.get("total24h")),
                    fees_7d_usd=_num(fee.get("total7d")),
                    fees_30d_usd=_num(fee.get("total30d")),
                    revenue_24h_usd=_num(rev.get("total24h")),
                    revenue_7d_usd=_num(rev.get("total7d")),
                    revenue_30d_usd=_num(rev.get("total30d")),
                    holders_revenue_24h_usd=_num(hol.get("total24h")),
                    holders_revenue_30d_usd=_num(hol.get("total30d")),
                )
            )

        snapshots = self._dedupe_by_gecko_id(candidates)
        logger.info(
            "provider_fetch_ok",
            provider=self.name,
            protocols=len(candidates),
            snapshots=len(snapshots),
        )
        return snapshots

    @staticmethod
    def _dedupe_by_gecko_id(
        candidates: list[RawFundamentalSnapshot],
    ) -> list[RawFundamentalSnapshot]:
        """Keep one snapshot per gecko_id — the largest-TVL representative.

        Avoids double-counting when several protocols map to the same token
        (Phase 1 rule). Deterministic: TVL desc, then slug asc.
        """
        best: dict[str, RawFundamentalSnapshot] = {}
        for snap in candidates:
            key = snap.gecko_id or ""
            current = best.get(key)
            if current is None:
                best[key] = snap
                continue
            cur_tvl = current.tvl_usd or 0.0
            new_tvl = snap.tvl_usd or 0.0
            # Larger TVL wins; on a tie the lexicographically smaller slug wins.
            if new_tvl > cur_tvl or (new_tvl == cur_tvl and snap.slug < current.slug):
                best[key] = snap
        return list(best.values())

    def close(self) -> None:
        """Close the underlying client if this provider created it."""
        if self._owns_client and self._client is not None:
            self._client.close()
            self._client = None
