# API Documentation

Home for AlphaDex Scout's API contracts. The API is a FastAPI application; it also
serves interactive OpenAPI docs at `/docs`.

Resources are designed per-sprint, not built speculatively. Implemented so far:

- `GET /health` — application / database health (Sprint 01)
- `GET /assets`, `GET /assets/{id}` — asset universe (Sprint 02)
- `GET /market-data` — latest market observations (Sprint 02)

Planned: `/fundamentals`, `/tokenomics`, `/opportunities`, `/scores`,
`/divergences`, `/risk`.

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

## Conventions

- Errors do not leak internal stack traces to consumers (AGENTS.md §8, §12).
- Timestamps are ISO-8601 UTC. `age_seconds` is derived from `observed_at` at
  request time and indicates freshness.
