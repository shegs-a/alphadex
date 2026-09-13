# API Documentation

Home for AlphaDex Scout's API contracts. The API is a FastAPI application; it also
serves interactive OpenAPI docs at `/docs`.

Resources are designed per-sprint, not built speculatively. Implemented so far:

- `GET /health` — application / database health (Sprint 01)
- `GET /assets`, `GET /assets/{id}` — asset universe (Sprint 02)
- `GET /market-data` — latest market observations (Sprint 02)
- `GET /fundamentals` — latest fundamental observations (Sprint 03)
- `GET /opportunities`, `GET /opportunities/{id}`, `GET /scans` — scanner (Sprint 04)

Planned: `/tokenomics`, `/scores`, `/divergences`, `/risk`.

---

## `GET /health`

Returns application and database health. `200` when healthy; `503` when the
database is unreachable (the service never reports healthy with a critical
dependency down).

```json
{ "status": "ok", "version": "0.2.0",
  "checks": { "application": "ok", "database": "ok" } }
```

---

## `GET /assets`

The asset universe. Read-only. Ingestion is an operational command, not a public
write path.

Query parameters:

| Param    | Type | Default | Notes                     |
|----------|------|---------|---------------------------|
| `limit`  | int  | 100     | 1–500                     |
| `offset` | int  | 0       | ≥ 0 (pagination)          |

Response — `200`, a list of assets:

```json
[
  { "id": 1, "symbol": "BTC", "name": "Bitcoin", "category": null,
    "source_ids": [ { "provider": "coingecko", "external_id": "bitcoin" } ] }
]
```

## `GET /assets/{asset_id}`

One asset by id. `404` if not found. Same object shape as above.

---

## `GET /market-data`

The most recent observation per `(asset, metric, period)`. "Current value" is a
query over the append-only history (ADR-004), not a stored field.

Query parameters (all optional):

| Param      | Type | Notes                                   |
|------------|------|-----------------------------------------|
| `asset_id` | int  | Filter to one asset.                    |
| `metric`   | str  | Filter to one metric, e.g. `market.price_usd`. |

Response — `200`, a list of observations:

```json
[
  { "asset_id": 1, "metric": "market.price_usd",
    "value": 61234.5, "value_status": "OK",
    "unit": "USD", "period": "point",
    "observed_at": "2026-09-12T12:00:00Z",
    "source_provider": "coingecko",
    "source_timestamp": "2026-09-12T12:00:00Z",
    "source_status": "ok", "age_seconds": 126.6 }
]
```

**Missing data is a status, never `0`.** When a provider does not supply a metric,
the observation is returned with `value: null` and a non-`OK` `value_status`
(e.g. `NOT_AVAILABLE`) — consumers must branch on `value_status`, not treat a
missing value as zero (ADR-003).

Available market metrics are listed in `docs/data/README.md`.

---

## `GET /fundamentals`

The most recent `fundamental.*` observation per `(asset, metric, period)` —
protocol fees, revenue, holders-revenue, and TVL. Same response shape and
missing-data semantics as `/market-data` (a missing metric is `value: null` with a
non-`OK` `value_status`, never `0`). Kept separate from `/market-data` to preserve
the domain boundary: this endpoint returns only `fundamental.*` metrics, and
`/market-data` returns only `market.*` metrics.

Query parameters (all optional):

| Param      | Type | Notes                                   |
|------------|------|-----------------------------------------|
| `asset_id` | int  | Filter to one asset.                    |
| `metric`   | str  | Filter to one metric, e.g. `fundamental.fees_usd.24h`. |

```json
[
  { "asset_id": 12, "metric": "fundamental.tvl_usd",
    "value": 30120702622.9, "value_status": "OK",
    "unit": "USD", "period": "point",
    "observed_at": "2026-09-12T22:10:06Z",
    "source_provider": "defillama",
    "source_timestamp": null, "source_status": "ok",
    "age_seconds": 42.0 },
  { "asset_id": 12, "metric": "fundamental.revenue_usd.24h",
    "value": null, "value_status": "NOT_AVAILABLE",
    "unit": "USD", "period": "24h", "observed_at": "2026-09-12T22:10:06Z",
    "source_provider": "defillama", "source_status": "ok", "age_seconds": 42.0 }
]
```

Fees, Revenue, Holders Revenue, and TVL are **distinct metrics** and are never
conflated. The full list is in `docs/data/README.md`.

---

## `GET /opportunities`

Ranked results from the **latest successful scan** — the Opportunity Scanner's
candidate list. Read-only; running a scan is an operational command, not a public
endpoint. Returns `[]` if no scan has run yet.

Query parameters (all optional):

| Param    | Type | Notes                                                   |
|----------|------|---------------------------------------------------------|
| `status` | str  | Filter: `candidate` / `watch` / `insufficient_data` / `excluded`. |
| `limit`  | int  | 1–500 (default 100).                                    |
| `offset` | int  | ≥ 0 (pagination).                                       |

Results are ordered by `rank` (ranked candidates/watches first, then the rest).
Each item carries the **preliminary Screen Score** (not the Alpha Score), data
completeness, and the per-criterion `reasons` (gates + signals) behind the decision.
A missing score is `null` with a status — never `0` (ADR-003). No BUY language (§10).

```json
[
  { "asset_id": 12, "symbol": "SOL", "name": "Solana",
    "status": "candidate", "screen_score": 0.9178, "rank": 1,
    "data_completeness": 1.0,
    "reasons": {
      "gates": [ { "name": "min_volume_24h", "passed": true,
                   "value": 1937648352.0, "threshold": 100000.0,
                   "detail": "24h volume at or above floor" } ],
      "signals": [ { "name": "activity", "present": true, "raw": 5.0e7,
                     "normalized": 0.92, "weight": 0.4 } ]
    } }
]
```

## `GET /opportunities/{asset_id}`

One asset's result from the latest scan, with full `reasons`. `404` if the asset was
not part of the latest scan.

## `GET /scans`

Recent scan runs (metadata + counts): `id`, `status`, `started_at`, `finished_at`,
`universe_size`, `candidate_count`. Newest first.

---

## Conventions

- Errors do not leak internal stack traces to consumers (AGENTS.md §8, §12).
- Timestamps are ISO-8601 UTC. `age_seconds` is derived from `observed_at` at
  request time and indicates freshness.
