"""Provider tests for the CoinGecko adapter.

Deterministic and offline: HTTP is stubbed with ``httpx.MockTransport`` — no live
API is ever called (AGENTS.md §11). Covers happy-path parsing plus the required
failure modes: rate limit, server error, transport error, and malformed shapes
(AGENTS.md §13).
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from alphadex.providers.base import (
    MalformedResponse,
    ProviderUnavailable,
    RateLimited,
)
from alphadex.providers.coingecko import CoinGeckoProvider

FIXTURE = Path(__file__).parent / "fixtures" / "coingecko_markets.json"


def _provider_returning(payload: object, status_code: int = 200) -> CoinGeckoProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    return CoinGeckoProvider(client=client)


def test_parses_market_entries_from_fixture() -> None:
    payload = json.loads(FIXTURE.read_text())
    provider = _provider_returning(payload)

    snapshots = provider.fetch_markets(ids=["bitcoin", "ethereum"])

    assert [s.external_id for s in snapshots] == ["bitcoin", "ethereum"]
    btc = snapshots[0]
    assert btc.symbol == "BTC"  # normalized to upper-case
    assert btc.name == "Bitcoin"
    assert btc.price_usd == 61234.5
    assert btc.market_cap_rank == 1
    assert btc.observed_at is not None
    assert btc.observed_at.tzinfo is not None


def test_absent_fields_become_none_not_zero() -> None:
    payload = json.loads(FIXTURE.read_text())
    provider = _provider_returning(payload)

    eth = provider.fetch_markets(ids=["ethereum"])[1]

    # Nulls in the payload must surface as None, never 0 (ADR-003).
    assert eth.fully_diluted_valuation_usd is None
    assert eth.max_supply is None
    assert eth.price_change_pct_30d is None
    assert eth.price_usd == 2456.78


def test_rate_limit_raises() -> None:
    provider = _provider_returning([], status_code=429)
    with pytest.raises(RateLimited):
        provider.fetch_markets(top_n=5)


def test_server_error_raises_unavailable() -> None:
    provider = _provider_returning([], status_code=503)
    with pytest.raises(ProviderUnavailable):
        provider.fetch_markets(top_n=5)


def test_transport_error_raises_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = CoinGeckoProvider(client=client)
    with pytest.raises(ProviderUnavailable):
        provider.fetch_markets(top_n=5)


def test_non_list_payload_is_malformed() -> None:
    provider = _provider_returning({"error": "nope"})
    with pytest.raises(MalformedResponse):
        provider.fetch_markets(top_n=5)


def test_entry_missing_identity_is_malformed() -> None:
    provider = _provider_returning([{"symbol": "btc", "name": "Bitcoin"}])
    with pytest.raises(MalformedResponse):
        provider.fetch_markets(top_n=5)
