# Sprint 02 Report — Market Data Foundation

## Sprint objective

Stand up the first real data pipeline: fetch market data from an external provider
**behind an interface**, validate and normalize it into append-only
`MetricObservation` rows with explicit missing-data semantics and full provenance,
and expose read-only `/assets` and `/market-data` endpoints — all exercised by
deterministic, offline tests.

## Completed tasks

- **Provider abstraction** (`src/alphadex/providers/`): `MarketDataProvider`
  interface, `RawMarketSnapshot` DTO, and a typed error hierarchy
  (`ProviderError`/`ProviderUnavailable`/`RateLimited`/`MalformedResponse`);
  `CoinGeckoProvider` (sync httpx, injectable client, optional API key, 429/5xx/
  transport handling); a config-driven `factory.build_market_data_provider`.
- **Market Data + Normalization** (`src/alphadex/marketdata/`): `normalize`
  (raw → `market.*` observations with units/periods; absent values → explicit
  `ValueStatus`, never `0`); `service.MarketDataService` (universe fetch, asset
  resolution, per-asset SAVEPOINT failure isolation, ingestion-run recording);
  `repository` (latest observation per asset/metric/period).
- **Schema** (migration `0002`, additive/reversible): `asset_source_ids`
  (`(provider, external_id)` identity, symbol-collision safe) and `ingestion_runs`
  (run-level observability). New ORM models `AssetSourceId`, `IngestionRun`.
- **API**: `GET /assets`, `GET /assets/{id}`, `GET /market-data` (read-only),
  surfacing `value_status`, provenance, and freshness (`age_seconds`).
- **Ops**: `scripts/ingest_market_data.py` one-shot ingestion (`--ids`/`--top-n`);
  Dockerfile ships `scripts/`.
- **Config**: `market_data_provider`, `coingecko_*`, `provider_timeout_seconds`,
  and a configurable universe (`market_universe_ids` / `market_universe_top_n`);
  `.env.example` updated.
- **Tests** (+22): provider parsing/errors (httpx `MockTransport`, fixtures),
  normalization + missing-data, ingestion service (collision, append-only,
  failure isolation, run record), API (`/assets`, `/market-data`), migration
  extended for `0002`.
- **Docs**: README (status/capabilities/setup/testing), CHANGELOG (`0.2.0`),
  `docs/data/` (market metric definitions + provenance), `docs/api/` (contracts),
  this report.

## Incomplete tasks

None within scope. A second provider and a background scheduler were explicitly
out of scope (deferred to later sprints).

## Files/modules changed

New: `src/alphadex/providers/{__init__,base,coingecko,factory}.py`,
`src/alphadex/marketdata/{__init__,normalize,service,repository}.py`,
`src/alphadex/api/routes/{assets,market_data}.py`,
`migrations/versions/0002_market_data_provenance.py`,
`scripts/ingest_market_data.py`,
`tests/{test_providers_coingecko,test_normalize,test_marketdata_service,
test_api_market_data}.py`, `tests/fixtures/coingecko_markets.json`,
`docs/sprints/sprint-02-plan.md`, this report.
Modified: `src/alphadex/models.py`, `src/alphadex/config.py`,
`src/alphadex/api/app.py`, `Dockerfile`, `tests/test_migration.py`, `README.md`,
`CHANGELOG.md`, `.env.example`, `docs/data/README.md`, `docs/api/README.md`.

## Database changes

Migration `0002` (additive, on top of `0001`): `asset_source_ids`
(`asset_id` FK, `provider`, `external_id`, `UNIQUE(provider, external_id)`, index
on `asset_id`) and `ingestion_runs` (`provider`, `status`, `started_at`,
`finished_at`, `assets_ok`, `assets_failed`, `observations_written`, `error`).
`assets` and `metric_observations` are unchanged. Market metrics are written as
append-only observations under the `market.*` namespace.

## API changes

Added read-only `GET /assets`, `GET /assets/{id}`, and `GET /market-data`
(latest observation per asset/metric/period, with `value_status`, provenance, and
`age_seconds`). `/health` unchanged. OpenAPI docs at `/docs` reflect the new
routes.

## Configuration changes

`.env.example` activates market-data provider settings (`MARKET_DATA_PROVIDER`,
`COINGECKO_BASE_URL`, optional `COINGECKO_API_KEY`, `PROVIDER_TIMEOUT_SECONDS`)
and a configurable universe (`MARKET_UNIVERSE_IDS` / `MARKET_UNIVERSE_TOP_N`).
No secrets committed.

## Tests executed

```
uv run pytest                              # full suite
uv run ruff check .                        # lint
uv run ruff format --check .               # format
uv run mypy src                            # type check
python3 -m unittest tests.test_foundation  # dependency-free gate
docker compose up --build                  # container path (PostgreSQL 16)
docker compose exec app python scripts/ingest_market_data.py --ids bitcoin,ethereum,solana
```

## Test results

- **pytest: 43 passed** (21 from Sprint 01 + 22 new: providers 8, normalization 4,
  ingestion service 6, API 5; migration extended for `0002`).
- **ruff: all checks passed; format clean. mypy: success (19 source files).**
- **Foundation gate: 7 passed.**
- **Migration:** `alembic upgrade head` creates `asset_source_ids` and
  `ingestion_runs`; `downgrade base` reverses them (verified in `test_migration`).
- **End-to-end (Docker + PostgreSQL 16):** migration `0002` applied on startup; a
  live CoinGecko ingestion of `bitcoin,ethereum,solana` returned status `success`,
  3 assets, **33 observations**; `/market-data` returned real prices and, for
  ETH/SOL `max_supply`, `value: null` with `value_status: NOT_AVAILABLE` — the
  missing-data contract holding against a real provider (never `0`).

## Bugs discovered / fixed

- **Orphan asset on per-asset failure (found in review, fixed before commit):** an
  asset that failed mid-ingest could leave a half-created `assets`/
  `asset_source_ids` row (flushed before the failure) with no observations. Wrapped
  each asset in a `SAVEPOINT` (`session.begin_nested()`) so a failure rolls back
  that asset entirely; the isolation test asserts no orphan remains.

## Known limitations

- Single market-data provider (CoinGecko); free/demo tier. No fundamentals,
  tokenomics, scoring, divergence, valuation, or risk yet (Sprint 03+).
- No background scheduler — ingestion is run on demand.
- `latest_observations` uses a portable group-by/max-`observed_at` join; if two
  observations share an identical `observed_at` for the same asset/metric/period,
  both could return. Not expected from a single provider per run; revisit if a
  provider emits identical timestamps.
- Synchronous provider/DB access (sufficient at current scale).

## Technical debt

- Provider retry/backoff is minimal (errors are surfaced, not retried); add a
  retry policy when ingestion becomes scheduled/high-volume.
- Category is not yet populated (nullable); classification is a later concern.
- `pytest-asyncio` remains installed but unused (future async provider tests).

## Deviations from the plan

- Added `COPY scripts ./scripts` to the Dockerfile so the ingestion command runs
  inside the container (`docker compose exec app python scripts/...`). Minor,
  anticipated by the plan's optional container-verification step.
- Per-asset isolation implemented with a SAVEPOINT (stronger than the plan's
  "record and skip" wording) to guarantee no partial asset is persisted.

## Architecture decisions

No new ADRs. Implements ADR-001 (modular monolith — new Market Data,
Normalization, and provider modules), ADR-002 (stack — httpx provider, no new
deps), ADR-003 (explicit missing-data through normalization and the check
constraint), ADR-004 (append-only observations; "current" is a query). Provider
abstraction per AGENTS.md §2/§13.

## Release/version created

- Version: **v0.2.0** (market data foundation, container-verified).
- Commit: release commit on branch `claude/resume-session-devices-ibdww4`.
- Tag/Release: annotated tag `v0.2.0` at the release head, pushed to origin (the
  branch-scoped credential limitation seen in earlier remote sessions does not
  apply on the current machine). A GitHub Release can be published from the tag via
  the UI if desired.

## Rollback procedure

- `alembic downgrade -1` drops `asset_source_ids` and `ingestion_runs` (Sprint 01
  schema untouched); the new modules are inert until ingestion runs, so `/health`
  and the app path are unaffected.
- `git checkout v0.1.0` returns to the platform foundation. `v0.1.0` remains the
  prior stable anchor; `v0.2.0` becomes the new one.

## Recommended next steps (Sprint 03 — Fundamental Intelligence)

1. Define `FundamentalDataProvider` behind the same interface pattern; add a first
   provider (e.g. DefiLlama) for Fees/Revenue/TVL — kept strictly distinct from
   market metrics (AGENTS.md §9).
2. Normalize fundamentals into `metric_observations` under a `fundamental.*`
   namespace with provenance and explicit missing-data.
3. Add read endpoints for fundamentals; extend ingestion (and consider a scheduler
   once multiple providers must run periodically).
4. Begin the raw→normalized validation layer needed for divergence (Sprint 05).
