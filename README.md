# AlphaDex Scout

**Crypto Alpha Intelligence System — by Ciphercrib Solutions**

AlphaDex Scout is the first working version of AlphaDex. It identifies potentially
**mispriced** crypto assets by finding **evidence-backed divergence** between
improving economic fundamentals and lagging market price/valuation.

> Core thesis: *"Find crypto assets where underlying economic activity and
> fundamentals are improving materially faster than market price/valuation is
> recognizing."*

It is **not** a pump predictor and **not** a generic dashboard. It is an
intelligence system that supports human decisions with evidence.

---

## Why it exists

The market frequently fails to price protocol reality. AlphaDex Scout looks for
situations where economic activity, revenue, or usage is rising while price,
market cap, or valuation is not — then evaluates whether that improvement actually
accrues value to the token, whether the token is attractively valued, and what the
risks are. It carefully distinguishes four things that are often conflated:

1. A protocol becoming economically stronger.
2. A token benefiting from that strength.
3. A token being attractively valued.
4. A technically actionable entry existing.

The analysis pipeline:

```
Asset Universe → Market Data → Fundamental Data → Tokenomics → Normalization
  → Divergence Detection → Valuation → Risk → Alpha Score
  → Ranked Opportunities → Human-readable Explanation
```

Outputs are always **explainable** (why interesting, why now, what changed, what
supports/contradicts the thesis, what could invalidate it, the major risk) and
separate **Alpha Score**, **Risk Score**, and **Confidence**. There are no blind
BUY signals.

---

## Architecture overview

A **modular monolith**: a single deployable application with strong internal module
boundaries (Market Data, Fundamental Data, Tokenomics, Normalization, Opportunity
Scanner, Divergence, Valuation, Risk, Scoring, Technical Analysis, Reporting,
Notifications, API). It runs identically on a laptop and on a small cloud VM via
Docker Compose.

```
                 ┌──────────────────┐
                 │   API / Service  │   (FastAPI)
                 └────────┬─────────┘
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
 Market Intelligence  Fundamental        Alpha Engine
                      Intelligence     (divergence/valuation/
                                        risk/scoring)
       └──────────────────┼──────────────────┘
                          ▼
                    PostgreSQL
```

See `docs/architecture/overview.md` and the ADRs in `docs/decisions/` for the
reasoning behind these choices.

---

## Technology stack

Python 3.11+ · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · pydantic-settings ·
httpx · APScheduler · structlog · pytest · ruff · mypy · uv · Docker + Compose.

Rationale in `docs/decisions/ADR-002-technology-stack.md`.

---

## Prerequisites

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/) (Python packaging/env)  *(used from Sprint 01)*
- Docker + Docker Compose  *(used from Sprint 01)*
- Git

---

## Current status

**Sprint 00 — Architecture & Engineering Foundation.**

This repository currently contains the engineering foundation only: documentation,
architecture decisions, sprint process, and a runnable foundation test gate. The
application code, database, Docker environment, and health endpoint are **planned
for Sprint 01 (Platform Foundation)** and are intentionally not yet present.

### Current capabilities
- Documented mission, architecture principles, and coding/data/scoring rules
  (`AGENTS.md`).
- Architecture decision records for the modular monolith, technology stack,
  missing-data representation, and historical observations model.
- Sprint process with plan/report templates and the Sprint 00 plan + report.
- A dependency-free foundation test gate verifying the repository structure.

### Known limitations
- No application, API, database, or Docker environment yet (Sprint 01).
- No data providers, scoring, or pipeline yet (Sprint 02+).

---

## Setup

### Foundation test gate (available now, no dependencies)

```bash
python3 -m unittest discover -s tests -v
```

### Local development (from Sprint 01)

```bash
uv sync                                         # install dependencies
cp .env.example .env                            # configure (never commit .env)
uv run alembic upgrade head                     # apply migrations
uv run uvicorn alphadex.api.app:app --reload    # run the API
```

### Docker (from Sprint 01)

```bash
cp .env.example .env
docker compose up --build
# health check
curl http://localhost:8000/health
```

---

## Environment variables

Configuration is env-driven; see `.env.example` for the documented set. Never
commit real secrets. Variables expand as the system grows (database URL, provider
API keys, scan settings). `.env.example` is the source of truth for what is
configurable.

---

## Testing

| Command | Scope |
|---|---|
| `python3 -m unittest discover -s tests -v` | Foundation gate (now) |
| `uv run pytest` | Full suite (Sprint 01+) |
| `uv run pytest -m "not integration"` | Unit/data-quality only (Sprint 01+) |

Tests are deterministic and must not depend on live external APIs; providers are
mocked with fixtures.

---

## Development workflow

1. Read `AGENTS.md`.
2. Read the relevant `docs/sprints/sprint-NN-plan.md`.
3. Inspect only the relevant code.
4. Implement the approved sprint scope.
5. Run targeted tests, then regression tests.
6. Update `docs/sprints/sprint-NN-report.md`, `README.md`, and `CHANGELOG.md`.
7. Review the diff, create a stable commit, tag the release.

### Sprint Completion checklist

```
[ ] All in-scope tasks implemented   [ ] Docker builds & starts
[ ] Out-of-scope work excluded       [ ] Migrations verified
[ ] Unit tests pass                  [ ] API/health checks verified
[ ] Integration tests pass           [ ] Docs + README + CHANGELOG updated
[ ] Regression tests pass            [ ] Sprint report completed
[ ] Known limitations documented     [ ] Technical debt documented
[ ] Git diff reviewed                [ ] Stable commit + version tag created
[ ] Rollback point confirmed
```

---

## Documentation map

- `AGENTS.md` — persistent engineering rules (read first).
- `docs/architecture/` — system overview and diagrams.
- `docs/decisions/` — architecture decision records (ADRs).
- `docs/data/` — data model, metric definitions, provenance.
- `docs/api/` — API contracts.
- `docs/sprints/` — per-sprint plans and reports.
- `CHANGELOG.md` — release history.

---

## License & ownership

Proprietary — Ciphercrib Solutions. All rights reserved.
