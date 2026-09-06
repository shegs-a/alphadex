# ADR-002: Technology Stack

- Status: Accepted
- Date: 2026-09-06
- Sprint: 00

## Context

The system needs a backend/API, a relational database, data ingestion, scheduled
jobs, an analytical/scoring engine, strong testing, Docker, and env-based
configuration. Selection criteria (from the spec): mature, well-supported, easy to
run locally, Docker- and cloud-friendly, good for data processing, maintainable by
a small team, cost-efficient, and easy for AI coding agents to work with. Avoid a
frontend framework until a real UI requirement exists.

## Decision

| Concern | Choice | Why |
|---|---|---|
| Language | **Python 3.11+** (3.12 in Docker) | Best ecosystem for data processing and provider integrations; ubiquitous; AI-agent friendly. Local env is 3.11, so 3.11 is the floor. |
| API framework | **FastAPI + Uvicorn** | Mature, async, automatic OpenAPI docs, pydantic validation; right size (not as heavy as Django, more batteries than Flask). |
| Database | **PostgreSQL 16** | Relational, mature, excellent for historical observations and analytical queries; JSONB for flexible provider metadata. |
| ORM | **SQLAlchemy 2.0** | De-facto standard, typed, async-capable, parameterized queries by default. |
| Migrations | **Alembic** | Standard companion to SQLAlchemy; versioned, reversible schema changes. |
| Config | **pydantic-settings** | Typed, validated, env-driven configuration. |
| HTTP client | **httpx** | Async, modern, testable; pairs with FastAPI. |
| Scheduling | **APScheduler** (in-process) | Runs scheduled ingestion inside the monolith; no external broker (per ADR-001). |
| Logging | **structlog** | Structured logs (asset/provider/outcome/why). |
| Testing | **pytest**, pytest-asyncio, FastAPI/httpx test client | Powerful, fixtures/mocks, deterministic. |
| Lint/format | **ruff** | Fast, replaces black+flake8+isort. |
| Type checking | **mypy** | Enforces the typed conventions in AGENTS.md. |
| Packaging/env | **uv** + `pyproject.toml` | Fast, reproducible locking; available in the environment (0.8.x). |
| Containers | **Docker + Docker Compose** | Local/cloud parity per ADR-001. |

No frontend framework yet (dashboard deferred to Sprint 10).

## Alternatives considered

- **Django** instead of FastAPI: batteries-included but heavier and ORM-opinionated;
  more than needed for an API + pipeline. **Flask**: lighter but lacks native async
  and built-in validation/OpenAPI. FastAPI is the middle ground.
- **MongoDB / a time-series DB** instead of PostgreSQL: rejected — the spec favors a
  relational core and warns against JSON-blob-everything; Postgres + JSONB covers
  flexible metadata without a second datastore.
- **Celery + Redis/RabbitMQ** for scheduling: rejected for now — adds a broker and
  operational surface with no current scale need; APScheduler in-process suffices
  (ADR-001). Revisit if job isolation/throughput demands it.
- **pip/poetry** instead of uv: both viable; uv chosen for speed and reproducible
  locking and because it is already present. pip remains a fallback.
- **Node/TypeScript backend**: rejected — Python's data ecosystem and the spec's
  guidance make Python the better fit for this analytical workload.

## Rationale

Every choice is mature, Docker- and cloud-friendly, well-documented (hence
AI-agent friendly), and cost-efficient (no extra managed infrastructure). The stack
keeps the modular monolith simple while leaving room to grow (async throughout,
JSONB for flexibility, migrations for safe schema evolution).

## Consequences

- **Positive:** one language across API/ingestion/analytics; strong typing and
  testing; trivial local/cloud parity; low operational cost.
- **Negative:** Python CPU-bound analytics can be slower than compiled languages —
  acceptable at Scout scale and mitigated by tiered processing and vectorized
  libraries later if needed.
- Concrete versions are pinned in `pyproject.toml` when Sprint 01 introduces it;
  dependency additions follow the discipline in AGENTS.md §14.
