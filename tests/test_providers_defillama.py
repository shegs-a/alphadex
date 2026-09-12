"""Provider tests for the DefiLlama fundamentals adapter.

Deterministic and offline: HTTP is stubbed with ``httpx.MockTransport`` routing by
endpoint and ``dataType`` — no live API is called. Covers the multi-call assembly,
gecko_id dedupe, dropping of protocols without a gecko_id, explicit missing-data,
and the failure modes.
"""

from __future__ import annotations

import httpx
import pytest

from alphadex.providers.base import (
    MalformedResponse,
    ProviderUnavailable,
    RateLimited,
)
from alphadex.providers.defillama import DefiLlamaProvider

_PROTOCOLS = [
    {
        "slug": "uniswap",
        "name": "Uniswap",
        "gecko_id": "uniswap",
        "symbol": "uni",
        "category": "Dexes",
        "tvl": 5_000_000_000.0,
    },
    {
        "slug": "uniswap-v2",  # same gecko_id, lower TVL → dropped by dedupe
        "name": "Uniswap V2",
        "gecko_id": "uniswap",
        "symbol": "uni",
        "category": "Dexes",
        "tvl": 1_000_000_000.0,
    },
    {
        "slug": "aave",
        "name": "Aave",
        "gecko_id": "aave",
        "symbol": "aave",
        "category": "Lending",
        "tvl": 12_000_000_000.0,
    },
    {
        "slug": "no-gecko",  # no gecko_id → cannot be matched → dropped
        "name": "No Gecko",
        "gecko_id": None,
        "symbol": "ngk",
        "category": "Other",
        "tvl": 3.0,
    },
]

_FEES = {
    "protocols": [
        {"slug": "uniswap", "total24h": 2_000_000.0, "total7d": 1.4e7, "total30d": 6e7},
        {"slug": "uniswap-v2", "total24h": 5.0e5, "total7d": 3.5e6, "total30d": 1.5e7},
        {"slug": "aave", "total24h": 100_000.0, "total7d": 700_000.0, "total30d": 3e6},
    ]
}

_REVENUE = {
    "protocols": [
        # aave intentionally absent → revenue NOT_AVAILABLE
        {"slug": "uniswap", "total24h": 300_000.0, "total7d": 2.1e6, "total30d": 9e6},
    ]
}

_HOLDERS = {
    "protocols": [
        {"slug": "uniswap", "total24h": 50_000.0, "total30d": 1.5e6},
    ]
}


def _handler_ok(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    data_type = request.url.params.get("dataType")
    if path == "/protocols":
        return httpx.Response(200, json=_PROTOCOLS)
    if path == "/overview/fees":
        if data_type == "dailyRevenue":
            return httpx.Response(200, json=_REVENUE)
        if data_type == "dailyHoldersRevenue":
            return httpx.Response(200, json=_HOLDERS)
        return httpx.Response(200, json=_FEES)
    return httpx.Response(404, json={"error": "not found"})


def _provider(handler) -> DefiLlamaProvider:  # type: ignore[no-untyped-def]
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return DefiLlamaProvider(client=client)


def test_assembles_snapshots_and_dedupes_by_gecko_id() -> None:
    snaps = _provider(_handler_ok).fetch_fundamentals()

    by_gecko = {s.gecko_id: s for s in snaps}
    # uniswap + aave only; no-gecko dropped, uniswap-v2 collapsed into uniswap.
    assert set(by_gecko) == {"uniswap", "aave"}
    uni = by_gecko["uniswap"]
    assert uni.slug == "uniswap"  # higher-TVL representative
    assert uni.tvl_usd == 5_000_000_000.0
    assert uni.fees_24h_usd == 2_000_000.0
    assert uni.revenue_24h_usd == 300_000.0
    assert uni.holders_revenue_24h_usd == 50_000.0
    assert uni.symbol == "UNI"  # normalized upper-case


def test_missing_revenue_is_none_not_zero() -> None:
    snaps = _provider(_handler_ok).fetch_fundamentals()
    aave = next(s for s in snaps if s.gecko_id == "aave")
    # Fees present, revenue and holders-revenue absent → None (never 0).
    assert aave.fees_24h_usd == 100_000.0
    assert aave.revenue_24h_usd is None
    assert aave.holders_revenue_24h_usd is None


def test_holders_revenue_failure_is_non_fatal() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("dataType") == "dailyHoldersRevenue":
            return httpx.Response(500, json={"error": "boom"})
        return _handler_ok(request)

    snaps = _provider(handler).fetch_fundamentals()
    uni = next(s for s in snaps if s.gecko_id == "uniswap")
    assert uni.fees_24h_usd == 2_000_000.0  # fees still assembled
    assert uni.holders_revenue_24h_usd is None  # degraded gracefully


def test_rate_limit_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={})

    with pytest.raises(RateLimited):
        _provider(handler).fetch_fundamentals()


def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(ProviderUnavailable):
        _provider(handler).fetch_fundamentals()


def test_protocols_not_a_list_is_malformed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/protocols":
            return httpx.Response(200, json={"nope": True})
        return _handler_ok(request)

    with pytest.raises(MalformedResponse):
        _provider(handler).fetch_fundamentals()
