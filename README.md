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

**Sprint 05.1 — Economic Divergence Engine (refined).**

The heart of the thesis: detecting where a protocol's **fundamentals are improving
faster than the market's price/valuation recognizes**. For each candidate the
Scanner surfaces, the engine computes a fundamentals trend and a price/valuation
trend — from provider growth windows today (Track A) and, as history accumulates,
from the append-only observation history (Track B, preferred) — and **measures** the
gap. Crucially, it then **interprets** that measurement by the price regime,
distinguishing genuine divergence from repricing/momentum (ADR-005):
`potential_mispricing`, `fundamental_divergence`, `fundamental_repricing`,
`momentum`, `thesis_weakening`, `watch`, `insufficient_data`. Each signal keeps its
measurement (`divergence_gap`, `divergence_score`, `signal_strength`) separate from
its `data_quality`, and carries **explainable** evidence (what changed, why now,
supports/contradicts/invalidates, major risk, evidence strength). Results are served
read-only via `/divergences`. It is a **component**, not the final verdict — the real
Alpha/Risk/Confidence scoring comes later; ranking is a preliminary
divergence-measurement ranking, not an opportunity ranking; there is no blind BUY
language and thin data is surfaced honestly, never fabricated.

### Current capabilities
- Documented mission, architecture principles, and coding/data/scoring rules
  (`AGENTS.md`) + ADRs 001–004.
- FastAPI application with `GET /health` (200 healthy / 503 when the DB is down).
- PostgreSQL 16 via `docker compose up --build`, with healthchecks and a persistent
  volume; app applies migrations on startup.
- Core schema: `assets` + append-only `metric_observations` (missing data always
  explicit, never `0`), plus `asset_source_ids` (symbol-collision-safe identity)
  and `ingestion_runs` (run-level observability).
- **Two provider abstractions:** a CoinGecko adapter for `market.*` metrics
  (price, market cap, FDV, volume, supply, price change, rank) and a DefiLlama
  adapter for `fundamental.*` metrics (fees, revenue, holders-revenue, TVL) — each
  with units, periods, and provenance.
- **Opportunity Scanner** — a configurable screen (inclusion gates + a preliminary
  Screen Score) that ranks candidates and persists each scan (`scan_runs` /
  `scan_results`) with per-criterion evidence; missing data flagged, never
  zero-scored; no BUY language.
- **Economic Divergence Engine** — computes fundamentals vs price/valuation trends
  (Track A growth windows now; Track B cross-time history when available) for the
  Scanner's candidates and emits explainable, classified divergence signals
  (`divergence_runs` / `divergence_signals`) with a `data_quality` figure.
- **Ingestion + analysis commands** — `scripts/ingest_market_data.py`,
  `scripts/ingest_fundamentals.py`, `scripts/run_scan.py`, `scripts/run_divergence.py`.
- **Read API** — `GET /assets`, `GET /assets/{id}`, `GET /market-data`,
  `GET /fundamentals`, `GET /opportunities`, `GET /opportunities/{id}`, `GET /scans`,
  `GET /divergences`, `GET /divergences/{id}`, `GET /divergence-runs`.
- Test suite under pytest (config, health, data-quality, migration, providers,
  normalization, ingestion services, scanner, divergence, API) plus the foundation
  gate.

### Known limitations
- Divergence is a **component**, not a verdict. No tokenomics, valuation, risk, or
  the real three-part Alpha/Risk/Confidence scoring yet (Sprints 06–07).
- Divergence relies on **Track A** (single-snapshot provider growth windows) until
  observation history accumulates; **Track B** (cross-time, more rigorous) engages
  automatically per asset as history builds. History is built by running ingestion
  repeatedly; automated cadence (a scheduler) is deferred to Sprint 12.
- Fundamentals cover only assets already in the market universe (Phase 1 matches by
  `gecko_id`; unmatched protocols are skipped).
- No reporting, notifications, or dashboard yet. Database and provider access are
  synchronous (sufficient at current scale).

---

## Setup

### Docker (recommended)

```bash
cp .env.example .env          # configure (never commit .env)
docker compose up --build     # starts PostgreSQL + app; app applies migrations
curl http://localhost:8000/health
# interactive API docs: http://localhost:8000/docs

# ingest market data (one-shot), then read it back:
docker compose exec app python scripts/ingest_market_data.py --ids bitcoin,ethereum,solana
curl http://localhost:8000/assets
curl "http://localhost:8000/market-data?metric=market.price_usd"

# ingest protocol fundamentals (matched to the assets above by gecko_id):
docker compose exec app python scripts/ingest_fundamentals.py
curl "http://localhost:8000/fundamentals?metric=fundamental.tvl_usd"

# run the opportunity scanner, then read the ranked candidates:
docker compose exec app python scripts/run_scan.py
curl "http://localhost:8000/opportunities?status=candidate"

# run the divergence engine over the candidates, then read the signals:
docker compose exec app python scripts/run_divergence.py
curl "http://localhost:8000/divergences?classification=fundamental_divergence"
```

### Local development

```bash
uv sync --extra dev                             # install dependencies + dev tools
cp .env.example .env                            # set POSTGRES_HOST=localhost
uv run alembic upgrade head                     # apply migrations (needs a DB)
uv run uvicorn alphadex.api.app:app --reload    # run the API
uv run python scripts/ingest_market_data.py --top-n 25   # ingest market data
uv run python scripts/ingest_fundamentals.py             # then ingest fundamentals
uv run python scripts/run_scan.py                        # then run a scan
uv run python scripts/run_divergence.py                  # then run divergence
```

> A local PostgreSQL is required for `alembic upgrade` and a live `/health`. The
> quickest source is the compose DB service: `docker compose up -d db`.

### Foundation test gate (no dependencies)

```bash
python3 -m unittest tests.test_foundation -v
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
| `uv run pytest` | Full suite (config, health, data-quality, migration, providers, normalization, ingestion, API, foundation) |
| `python3 -m unittest tests.test_foundation -v` | Dependency-free foundation gate |
| `uv run ruff check . && uv run mypy src` | Lint + type check |

Tests are deterministic and run on in-memory SQLite (no external services);
PostgreSQL is exercised via Docker Compose. Provider integrations are stubbed with
`httpx.MockTransport` and JSON fixtures — tests never depend on live external APIs.

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
