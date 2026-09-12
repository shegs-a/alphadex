# Changelog

All notable changes to AlphaDex Scout are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Work toward the next release. Move entries under a version heading on release._

## [0.2.0] — 2026-09-12

### Added
- Market Data Foundation (Sprint 02):
  - `MarketDataProvider` interface, `RawMarketSnapshot` DTO, and a typed provider
    error hierarchy (`ProviderError`/`ProviderUnavailable`/`RateLimited`/
    `MalformedResponse`) — business logic depends only on the interface.
  - `CoinGeckoProvider` adapter (httpx; injectable client for offline tests) and
    a config-driven provider factory.
  - Normalization from raw snapshots into append-only `metric_observations` under
    a `market.*` metric namespace (price, market cap, FDV, volume, supply, price
    change %, rank) with units, periods, and provenance. Absent values are stored
    as an explicit `ValueStatus` (e.g. `NOT_AVAILABLE`), never `0` (ADR-003).
  - Ingestion service with per-asset SAVEPOINT isolation (one asset's failure is
    recorded and skipped, never aborting the run) and an `ingestion_runs` record.
  - `asset_source_ids` mapping `(provider, external_id)` → internal asset, so
    symbol collisions cannot merge distinct assets (AGENTS.md §13).
  - Alembic migration `0002` (additive, reversible) for the two new tables.
  - Read-only API: `GET /assets`, `GET /assets/{id}`, `GET /market-data`
    (surfacing `value_status`, provenance, and freshness — missing data as a
    status, never `0`).
  - `scripts/ingest_market_data.py` one-shot ingestion command over a configurable
    universe (`--ids` / `--top-n`); the Dockerfile now ships `scripts/`.
  - Provider/universe configuration in `config.py` and `.env.example`.

### Notes
- Verified end-to-end on Docker + PostgreSQL 16: migration `0002` applies, a live
  CoinGecko ingestion of three assets wrote 33 observations, and `/market-data`
  returned real values with unavailable metrics (e.g. ETH/SOL `max_supply`) as
  `NOT_AVAILABLE` rather than `0`. Full suite: 43 tests; ruff and mypy clean.

## [0.1.0] — 2026-09-06

### Added
- Platform foundation (Sprint 01):
  - FastAPI application (`alphadex.api.app:app`) with `GET /health` reporting
    application and database health (200 healthy, 503 when the database is down).
  - PostgreSQL 16 via Docker Compose (`docker-compose.yml` + `Dockerfile`) with
    healthchecks, `depends_on: service_healthy`, and a persistent `pgdata` volume.
  - SQLAlchemy 2.0 models: `Asset` and append-only `MetricObservation` with a
    `ValueStatus` enum and a check constraint enforcing that missing data is
    explicit and never stored as `0` (ADR-003 / ADR-004).
  - Alembic migrations (`0001_initial_schema`) wired to application settings.
  - Env-driven configuration (pydantic-settings) and structured logging (structlog).
  - `pyproject.toml` (uv) with pinned dependencies + `uv.lock`; ruff + mypy config.
  - Test suite under pytest (config, health, data-quality, migration smoke); the
    dependency-free foundation gate is retained and now run as a targeted module.

### Changed
- Foundation gate invocation is now `python3 -m unittest tests.test_foundation`
  (not `unittest discover`), with `uv run pytest` as the canonical test runner.

### Fixed
- `Dockerfile` now copies `README.md` into the image. `pyproject.toml` declares
  `readme = "README.md"`, so installing the project (`uv sync`) failed the image
  build without it. This closes the Sprint 01 container gate.

### Notes
- First working, runnable platform, verified end-to-end via `docker compose up
  --build` on Docker Desktop: the image builds, PostgreSQL 16 becomes healthy,
  Alembic migration `0001` applies, and `GET /health` returns
  `200 {"status":"ok","checks":{"application":"ok","database":"ok"}}`.

## [0.0.0] — 2026-09-06

### Added
- Engineering foundation for AlphaDex Scout (Sprint 00):
  - `AGENTS.md` — persistent engineering rules (mission, architecture, stack,
    Git/release, data, scoring, testing, security rules, cost controls).
  - `README.md` — product overview, architecture, setup, workflow.
  - Documentation structure: `docs/architecture/`, `docs/decisions/`,
    `docs/data/`, `docs/api/`, `docs/sprints/`.
  - Architecture Decision Records ADR-001 (modular monolith), ADR-002
    (technology stack), ADR-003 (missing-data representation), ADR-004
    (historical observations model).
  - Sprint process: plan/report templates, `sprint-00-plan.md`,
    `sprint-00-report.md`.
  - `.env.example` and `.gitignore`.
  - Dependency-free foundation test gate (`tests/`, stdlib `unittest`).

### Notes
- `0.0.0` marks the engineering foundation only. No application, database, Docker
  environment, or providers yet — those begin in Sprint 01 (Platform Foundation),
  targeting `v0.1.0`.
