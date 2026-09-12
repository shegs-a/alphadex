# Sprint 02 Plan — Market Data Foundation

## Objective

Stand up the first real data pipeline: fetch market data from an external
provider **behind an interface**, validate and normalize it into append-only
`MetricObservation` rows with full provenance, persist it with explicit
missing-data semantics (never `0`), and expose read-only `/assets` and
`/market-data` endpoints. The provider is swappable, ingestion isolates
per-asset failures, and every step is exercised by deterministic tests that use
fixtures — never a live API. Result: `scripts/ingest_market_data.py` populates
the schema from a configured universe, and the API serves what was ingested with
its source and freshness.

## Problem being solved

Sprint 01 delivered a runnable, empty platform: schema and `/health`, but no
data. Nothing can be discovered, scored, or diverged against without a trusted
flow of external data landing in the internal model. Sprint 02 builds that flow
for **market data** (price, market cap, FDV, volume, supply, price change) — the
cheapest, broadest tier of the pipeline (AGENTS.md §9) — and does so through the
provider abstraction (§2, §13) so the scoring engine never depends on a concrete
API. Getting the raw→normalized boundary, missing-data handling, and provenance
right here sets the pattern every later provider (fundamentals, tokenomics)
reuses.

## Scope

- **Provider interface + first concrete provider**
  - `src/alphadex/providers/base.py` — `MarketDataProvider` interface (ABC/
    Protocol), a raw snapshot DTO, and a typed error hierarchy
    (`ProviderError`, `ProviderUnavailable`, `RateLimited`, `MalformedResponse`).
  - `src/alphadex/providers/coingecko.py` — concrete `CoinGeckoProvider`
    (`.env.example` already names `coingecko`), sync `httpx.Client`, timeouts,
    rate-limit (HTTP 429) and error handling, optional API key. **No live calls
    in tests.**
- **Normalization + ingestion service** (module boundaries: Market Data ·
  Normalization, AGENTS.md §2)
  - `src/alphadex/marketdata/normalize.py` — map validated raw fields to
    `MetricObservation` rows: correct `metric` name, `unit`, `period`,
    `observed_at`, provenance; **missing/absent fields become an explicit
    `ValueStatus` (`NOT_AVAILABLE`/`UNKNOWN`), never `0`** (ADR-003).
  - `src/alphadex/marketdata/service.py` — orchestrate fetch → validate →
    normalize → persist for a configured universe; **isolate per-asset failures**
    (one asset's failure is recorded and skipped, never crashes the run,
    AGENTS.md §8); record an ingestion run.
  - `src/alphadex/marketdata/repository.py` — read queries: latest observation
    per (asset, metric), asset listing.
- **Asset identity / provider mapping** — a mapping from provider coin id to
  internal `Asset` so **symbol collisions and duplicate assets** (§13) are
  resolved by external id, not by ambiguous symbol.
- **Read API** (read-only; ingestion is a command, not a public write)
  - `GET /assets`, `GET /assets/{id}` — the asset universe.
  - `GET /market-data` — latest market observations, filterable by asset/metric,
    surfacing `value_status`, provenance, and freshness (never a bare `0`).
- **Ingestion entrypoint** — `scripts/ingest_market_data.py` (one-shot CLI) to
  run a fetch→persist cycle against the configured universe.
- **Config** — activate provider settings in `config.py` and `.env.example`:
  `MARKET_DATA_PROVIDER`, `COINGECKO_API_KEY` (optional), `COINGECKO_BASE_URL`,
  request timeout, and a **configurable universe** (e.g. `MARKET_UNIVERSE_TOP_N`
  or an explicit id list — the asset universe lives in config, §2).
- **Migration `0002`** — additive: provider-id mapping table and an
  ingestion-run log; working `downgrade()`.
- **Tests** — provider parsing (fixtures), normalization, missing-data,
  service ingestion (throwaway DB), asset resolution / collision, `/assets` +
  `/market-data`, data-quality; keep Sprint 01 suite and the foundation gate
  green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (metric definitions +
  provenance), and `docs/api/` (contracts for the new endpoints).

## Out of scope

- Fundamental data (Fees/Revenue/TVL — Sprint 03), tokenomics, divergence,
  valuation, risk, scoring, technical analysis, reporting, notifications,
  dashboard.
- A background scheduler (APScheduler). Sprint 02 ingests via an explicit
  command; periodic scheduling is deferred until there is a concrete need and is
  its own change.
- A second market-data provider. One concrete provider proves the interface;
  more are added later without touching the scoring/normalization code.
- Public write/ingestion-trigger endpoints. Ingestion is operational, not a
  public API.
- Async SQLAlchemy/HTTP. Stay sync to match Sprint 01 (§18 simplicity).

## Architecture impact

Introduces the first two runtime modules from the §2 boundary list — **Market
Data** and **Normalization** — plus a `providers/` package holding the interface
and the concrete adapter. Business logic depends only on `MarketDataProvider`;
the CoinGecko shape never leaks past `normalize.py`. No existing module is
modified except additive wiring (config, API router registration). Modular
monolith preserved (ADR-001); no new services/infrastructure.

## Data impact

- **New (migration `0002`, additive):**
  - `asset_source_ids` — `(asset_id, provider, external_id)` with
    `UNIQUE(provider, external_id)`, mapping a provider's coin id to an internal
    `Asset`. Resolves symbol collisions/duplicates (§13) deterministically.
  - `ingestion_runs` — run-level provenance/observability: `provider`,
    `started_at`, `finished_at`, `status`, `assets_ok`, `assets_failed`,
    `observations_written`, optional `error`. Makes failures observable (§8).
- **Reused unchanged:** `assets`, `metric_observations`. Market metrics are
  written as observations with `period` (`point` for spot price/market cap;
  `24h`/`7d`/`30d` for changes) and provenance (`source_provider`,
  `source_timestamp`, `source_status`).
- **Metric distinctions preserved (§9):** market metrics only (price, market
  cap, FDV, total volume, circulating/total/max supply, price change %). These
  are **not** fundamentals — Fees ≠ Revenue ≠ Price Appreciation is respected by
  keeping market data in its own metric namespace; fundamentals arrive in
  Sprint 03.
- **Missing data explicit (ADR-003):** any field the provider omits or returns
  null for is stored with a non-`OK` `ValueStatus`, never coerced to `0`. The
  existing check constraint enforces value-present-iff-`OK`.

## API impact

- `GET /assets` — paginated asset universe (`id`, `symbol`, `name`, `category`,
  source ids). `GET /assets/{id}` — one asset; `404` if unknown.
- `GET /market-data` — latest observation per (asset, metric); query params to
  filter by asset and/or metric. Each item carries `value`, `value_status`,
  `unit`, `period`, `observed_at`, `source_provider`, `source_timestamp`, and a
  computed freshness. Missing values are represented by `value_status`, never a
  misleading `0`. No stack traces leak to consumers (§8, §12). OpenAPI docs at
  `/docs` updated automatically.

## UI impact

None (dashboard deferred to Sprint 10).

## Implementation tasks

1. `providers/base.py` — interface, raw snapshot DTO, error hierarchy.
2. `providers/coingecko.py` — concrete provider (httpx, timeouts, 429/error
   handling, optional key); fixture-driven, no live calls in tests.
3. `config.py` + `.env.example` — provider + universe settings.
4. Migration `0002` — `asset_source_ids`, `ingestion_runs`; verify
   `upgrade`/`downgrade`.
5. `marketdata/normalize.py` — raw → observations with explicit missing-data and
   provenance.
6. `marketdata/service.py` — universe fetch, per-asset failure isolation, asset
   upsert + source-id resolution, run recording.
7. `marketdata/repository.py` + `api/routes/assets.py` + `api/routes/market_data.py`;
   register routers in `api/app.py`.
8. `scripts/ingest_market_data.py` — one-shot ingestion entrypoint.
9. Tests (unit, integration, API, data-quality); keep Sprint 01 + foundation
   gate green.
10. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
11. Optional local verification: run `scripts/ingest_market_data.py` against a
    small real universe once (documented, not a test dependency), then
    `docker compose up --build` to confirm the container path still holds.

## Testing strategy

- **Unit — provider:** parse a saved CoinGecko JSON fixture into the raw DTO;
  malformed/short response → `MalformedResponse`; HTTP 429 → `RateLimited`;
  network failure → `ProviderUnavailable`. HTTP is stubbed with
  `httpx.MockTransport` (no new dependency, no network).
- **Unit — normalization:** each raw field maps to the right `metric`/`unit`/
  `period`; a null/absent field yields the correct non-`OK` `ValueStatus` and a
  `NULL` value; provenance is populated; **nothing becomes `0`**.
- **Integration — service (throwaway SQLite DB):** ingesting a fixture snapshot
  creates `Asset`, `asset_source_ids`, `metric_observations`, and an
  `ingestion_runs` row; a per-asset error is recorded and does not abort the run;
  re-ingesting appends new observations (append-only, ADR-004) rather than
  mutating; two assets sharing a symbol resolve to distinct assets via source id
  (§13).
- **API:** `/assets` and `/market-data` return the documented shapes; unknown
  asset → `404`; a `NOT_AVAILABLE` metric is surfaced as status, not `0`.
- **Data-quality:** no `metric_observations` row has `value_status=OK` with a
  null value (or vice versa); provenance columns are populated for ingested
  rows.
- Deterministic and offline (fixtures + `MockTransport`); SQLite for portable
  runs, PostgreSQL via Docker/migration. Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes (new suites + Sprint 01);
  `python3 -m unittest tests.test_foundation` still passes.
- `alembic upgrade head` applies `0002` cleanly (and `downgrade` reverses it),
  creating `asset_source_ids` and `ingestion_runs`.
- The ingestion service, run on a fixture snapshot, persists assets +
  observations + a run record, with missing provider fields stored as explicit
  `ValueStatus` (never `0`) and full provenance.
- `GET /assets` and `GET /market-data` return the ingested data with source and
  freshness; missing values are represented by status, not `0`.
- Business logic depends only on `MarketDataProvider`; no CoinGecko-specific
  shape appears outside `providers/coingecko.py` and `normalize.py`.
- `ruff` clean, `mypy` clean; no out-of-scope modules (fundamentals/scoring/etc.)
  introduced.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` updated; Sprint 02 report
  completed.
- Release gate (AGENTS.md §7): tests pass → Docker builds → app starts →
  migrations apply → ingestion + read workflow works → docs updated → release
  commit → tag `v0.2.0` at the release head.

## Risks

- **Provider API shape drift / undocumented nulls.** Mitigation: validate at the
  provider boundary, snapshot fixtures for tests, explicit missing-data states.
- **Rate limits / free-tier limits (no key).** Mitigation: handle 429 as
  `RateLimited`, configurable timeout, small default universe; tests never call
  the network.
- **Symbol collisions / duplicate assets.** Mitigation: resolve by
  `(provider, external_id)` via `asset_source_ids`, not by symbol (§13).
- **Scope creep into fundamentals/scoring.** Mitigation: market metrics only;
  strict out-of-scope list.
- **SQLite vs PostgreSQL DDL differences** for `0002`. Mitigation: portable
  types, run the migration on both where possible (as in Sprint 01).

## Rollback considerations

Migration `0002` is additive with a working `downgrade()`:
`alembic downgrade -1` drops `asset_source_ids` and `ingestion_runs` (the
Sprint 01 schema is untouched). New modules are additive and inert until
ingestion is run, so the API/`/health` path is unaffected before or after
rollback. `git checkout v0.1.0` returns to the platform foundation; `v0.1.0`
remains the prior stable anchor and `v0.2.0` becomes the next once tagged.
