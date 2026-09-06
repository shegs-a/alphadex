# Sprint 01 Plan — Platform Foundation

## Objective

Deliver a working, testable, Dockerized application skeleton: a FastAPI service
with a `/health` endpoint reporting application **and** database health, PostgreSQL
via Docker Compose, SQLAlchemy 2.0 + Alembic migrations, env-driven configuration
(pydantic-settings), and structured logging (structlog). Establish the core
persistence schema that implements ADR-003 (explicit missing-data) and ADR-004
(append-only historical observations). Result: `docker compose up --build` yields a
running app whose `/health` verifies the database, with migrations applied and a
passing pytest suite.

## Problem being solved

Sprint 00 produced only documentation. Nothing runs yet. Sprint 01 turns the
decisions into an executable, reversible baseline that every later sprint (market
data, fundamentals, scoring) builds on — with the data-integrity contracts encoded
in real schema from the start so no later migration has to retrofit them.

## Scope

- `pyproject.toml` (uv) pinning the ADR-002 stack + dev tools (ruff, mypy, pytest);
  committed `uv.lock` for reproducibility.
- `src/alphadex/` package:
  - `config.py` — pydantic-settings, env-driven; assembles `DATABASE_URL`.
  - `logging.py` — structlog configuration.
  - `db.py` — SQLAlchemy engine/session (sync; see Deviations note in report).
  - `models.py` — `Base`, `Asset`, `MetricObservation`, `ValueStatus` enum, with a
    check constraint enforcing ADR-003 (value present iff status is OK).
  - `api/app.py` — FastAPI app factory + `app` instance.
  - `api/routes/health.py` — `/health` (application + database checks).
- Alembic (`migrations/`) + initial migration creating `assets` and
  `metric_observations`.
- `Dockerfile` + `docker-compose.yml` (app + PostgreSQL 16) with env config,
  healthchecks, `depends_on` on a healthy DB, and a persistent DB volume.
- `.env.example` — activate the database variables.
- Tests (`tests/`): unit (config, `/health` healthy and DB-down paths via test
  client), data-quality (missing data never coerced to `0`; check constraint holds),
  and a migration smoke test. Keep the Sprint 00 foundation gate green.
- Update `README.md` and `CHANGELOG.md`.

## Out of scope

- Data providers / ingestion, the scheduler (APScheduler), scoring, divergence,
  valuation, risk, technical analysis, reporting, notifications, dashboard.
- Any metric-specific business logic. The schema is generic; populating it is
  Sprint 02+.

## Architecture impact

Introduces the runtime application (modular-monolith skeleton per ADR-001), the DB
engine/session layer, and the API layer. No module boundaries are violated; only
`config`, `logging`, `db`, `models`, and `api` packages are created.

## Data impact

Creates the initial schema: `assets` and append-only `metric_observations`
(implementing ADR-004), with a `value_status` enum and a check constraint
implementing ADR-003 (missing data is explicit, never `0`). Managed by Alembic.

## API impact

Adds `GET /health` returning application + database health; `200` when healthy,
`503` when the database is unreachable (never reports healthy with a critical
dependency down). FastAPI serves OpenAPI docs at `/docs`.

## UI impact

None (dashboard deferred to Sprint 10).

## Implementation tasks

1. `pyproject.toml` + `uv sync` (+ commit `uv.lock`).
2. `config.py`, `logging.py`, `db.py`.
3. `models.py` with `Asset`, `MetricObservation`, `ValueStatus`, check constraint.
4. `api/app.py`, `api/routes/health.py`.
5. Alembic init + `env.py` wired to settings/Base + initial migration.
6. `Dockerfile`, `docker-compose.yml`, expand `.env.example`.
7. Tests + run `uv run pytest`; keep `unittest` foundation gate green.
8. Verify `alembic upgrade head`; verify Docker build/startup where the environment
   permits (document honestly if it does not).
9. Update README/CHANGELOG; write the Sprint 01 report; prepare release `v0.1.0`.

## Testing strategy

- **Unit:** settings parsing; `/health` returns 200 + `database: ok` on a working
  DB; `/health` returns 503 + `database: down` when the DB is unreachable (via a
  broken engine / dependency override).
- **Data-quality:** the check constraint rejects `value_status=OK` with null value
  and rejects a non-OK status with a non-null value; confirms missing data is never
  silently stored as `0`.
- **Migration smoke:** `alembic upgrade head` creates the expected tables on a
  throwaway database.
- Deterministic tests run on SQLite (no external services); Postgres is exercised
  via Docker Compose and the migration check. Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes; `python3 -m unittest discover -s tests -v` still passes.
- `alembic upgrade head` applies cleanly and creates `assets` +
  `metric_observations`.
- `/health` returns 200 with `application: ok` and `database: ok` against a live DB,
  and 503 with `database: down` when the DB is unavailable.
- `docker compose up --build` starts app + PostgreSQL with healthchecks (verified,
  or the limitation documented in the report).
- No out-of-scope modules (providers/scoring/etc.) introduced.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + Sprint 01 report updated.
- Stable commit on `claude/resume-session-devices-ibdww4`; release `v0.1.0`
  prepared (tag/release created by the owner if the session cannot push tags, as in
  Sprint 00).

## Risks

- **Docker build/compose may be constrained in this session's environment.**
  Mitigation: keep the pytest suite DB-agnostic (SQLite) so correctness is provable
  without Docker; document any Docker limitation honestly rather than claiming
  success.
- **SQLite vs PostgreSQL DDL differences.** Mitigation: use portable column types
  and `native_enum=False`; run the migration on both where possible.
- **Sync vs async SQLAlchemy.** Chosen sync for simplicity at this scale
  (maintainability/operational-simplicity over performance); revisit if needed.
- **Dependency footprint.** Mitigation: pin via `uv.lock`; only ADR-002 libraries.

## Rollback considerations

The initial migration is additive (creates new tables) with a working
`downgrade()`. Rollback options: `alembic downgrade -1` to drop the new tables, or
`git checkout v0.0.0` to return to the documentation-only foundation. `v0.0.0`
remains the prior stable anchor; `v0.1.0` becomes the new one.
