# Sprint 01 Report — Platform Foundation

## Sprint objective

Turn the Sprint 00 decisions into a working, testable, Dockerized application
skeleton: FastAPI + `/health` (application + database), PostgreSQL via Docker
Compose, SQLAlchemy 2.0 + Alembic, env-driven config, structured logging, and the
core persistence schema encoding ADR-003 and ADR-004.

## Completed tasks

- `pyproject.toml` (uv) pinning the ADR-002 stack + dev tools; `uv.lock` committed.
- `src/alphadex/`:
  - `config.py` — pydantic-settings; resolves `DATABASE_URL` or assembles it from
    `POSTGRES_*`.
  - `logging.py` — structlog JSON logging.
  - `db.py` — sync SQLAlchemy engine/session, `check_database()`, test reset hook.
  - `models.py` — `Base`, `Asset`, `MetricObservation`, `ValueStatus` (StrEnum),
    with a check constraint enforcing value-present-iff-status-OK (ADR-003) and an
    append-only observations design (ADR-004).
  - `api/app.py` — FastAPI app factory + `app`.
  - `api/routes/health.py` — `/health` (200 healthy, 503 when DB down).
- Alembic (`alembic.ini`, `migrations/env.py`, `script.py.mako`) + initial
  migration `0001_initial_schema` creating `assets` and `metric_observations`.
- `Dockerfile` (uv, reproducible, migrates then serves) and `docker-compose.yml`
  (PostgreSQL 16 + app, healthchecks, `depends_on: service_healthy`, persistent
  `pgdata` volume).
- `.env.example` database variables activated.
- Tests: `test_config`, `test_health`, `test_models_data_quality`,
  `test_migration`, plus the retained foundation gate; `conftest.py` (SQLite).
- README + CHANGELOG updated; foundation-gate invocation changed to a targeted
  module in AGENTS.md / README / tests/README.

## Incomplete tasks

- Docker build/compose could not be executed in this session (no Docker daemon —
  see Known limitations). Compose file validated with `docker compose config`.

## Files/modules changed

New: `pyproject.toml`, `uv.lock`, `Dockerfile`, `docker-compose.yml`,
`alembic.ini`, `src/alphadex/**`, `migrations/**`, `tests/{conftest,test_config,
test_health,test_models_data_quality,test_migration}.py`,
`docs/sprints/sprint-01-plan.md`, this report.
Modified: `AGENTS.md`, `README.md`, `.env.example`, `tests/README.md`,
`tests/test_foundation.py` (unused import removed by ruff).

## Database changes

Initial schema (migration `0001`): `assets` (symbol/name/category + timestamps,
unique symbol+name) and append-only `metric_observations` (metric, value,
`value_status` enum, unit, period, observed_at, provenance columns) with a check
constraint (`ck_observation_value_status_consistency`) and a composite index on
`(asset_id, metric, period, observed_at)`.

## API changes

Added `GET /health` → `{status, version, checks:{application, database}}`; 200 when
the DB is reachable, 503 when it is not. OpenAPI docs at `/docs`.

## Configuration changes

`.env.example` activates `POSTGRES_*` (with `DATABASE_URL` override). Config is read
via pydantic-settings; no secrets committed.

## Tests executed

```
uv run pytest                              # full suite
uv run ruff check .                        # lint
uv run ruff format --check .               # format
uv run mypy src                            # type check
python3 -m unittest tests.test_foundation  # dependency-free gate
uv run alembic upgrade head                # against a real (SQLite) DB
# + live boot: uvicorn serving /health returned 200 with database: ok
```

## Test results

- **pytest: 21 passed** (config 2, foundation 7, health 2, migration 1,
  data-quality 9).
- **ruff: all checks passed; format clean.**
- **mypy: success, no issues in 9 source files.**
- **Foundation gate: 7 passed** (targeted module run).
- **Migration:** `alembic upgrade head` created `assets` + `metric_observations`;
  `downgrade base` dropped them (verified in `test_migration`) and a live upgrade
  against a real DB succeeded.
- **End-to-end:** app booted via uvicorn against a real database engine and
  `/health` returned `200 {"status":"ok",...,"database":"ok"}`.

## Bugs discovered / fixed

- `unittest discover` began importing the new pytest-style modules under system
  Python (no deps) and failing. Fixed by making the dependency-free gate a targeted
  module invocation (`python3 -m unittest tests.test_foundation`) and documenting
  `uv run pytest` as the canonical runner. No product code affected.

## Known limitations

- **Docker not executed in this session:** no Docker daemon/socket is available in
  the remote environment, so `docker compose up --build` was not run here. The
  compose file validates (`docker compose config`), and the app + migrations were
  verified end-to-end against a real database engine (SQLite). PostgreSQL-specific
  and container startup verification should be completed by running
  `docker compose up --build` on a machine with Docker (the intended local/VM
  target).
- Database access is synchronous (adequate at current scale).
- No providers/ingestion/scoring yet (Sprint 02+).

## Technical debt

- PostgreSQL-specific migration/run verification is deferred to an environment with
  Docker; SQLite covers portable behavior and the check constraint.
- `pytest-asyncio` is installed for future async provider tests but unused so far.
- No CI workflow yet; commands are documented and ready to wire up.

## Deviations from the plan

- **Sync SQLAlchemy** chosen over async for simplicity (AGENTS.md §18: operational
  simplicity/maintainability over performance at this scale). Recorded here rather
  than as a new ADR since it is reversible and localized to `db.py`.
- Docker startup verification not performed in-session (environment limitation, as
  anticipated in the plan's Risks).

## Architecture decisions

No new ADRs. Implements ADR-001 (modular monolith skeleton), ADR-002 (stack),
ADR-003 (missing-data check constraint), ADR-004 (append-only observations).

## Release/version created

- Target version: **v0.1.0** (first working platform foundation).
- Commit: on branch `claude/resume-session-devices-ibdww4`.
- Tag/Release: to be created as `v0.1.0` at the release commit. As in Sprint 00,
  the session's git credential is branch-scoped and cannot push `refs/tags/*`, and
  no release-creation MCP tool is available; the repository owner should create the
  `v0.1.0` tag/release via the GitHub UI (or `git tag` from an unscoped clone)
  targeting the release commit once pushed.

## Rollback procedure

- `alembic downgrade base` drops the Sprint 01 tables, or `alembic downgrade -1`.
- `git checkout v0.0.0` returns to the documentation-only foundation.
- `v0.1.0` becomes the new stable anchor once tagged.

## Recommended next steps (Sprint 02 — Market Data Foundation)

1. Define `MarketDataProvider` interface + a first concrete provider behind it,
   with validation/normalization into `MetricObservation` (raw → normalized).
2. Add provider error handling (missing/stale/rate-limit/malformed) recording
   explicit missing-data states, never `0`.
3. Persist market metrics as observations with provenance; add `/assets` +
   `/market-data` read endpoints.
4. Add provider unit tests with fixtures (no live APIs) and a DB integration test.
5. Run `docker compose up --build` on a Docker-capable host to close the Sprint 01
   container gate, then proceed.
