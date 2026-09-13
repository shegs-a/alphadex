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

**Sprint 08 — Valuation Engine.**

Answers "is this asset cheap or expensive **relative to the economics it generates**?"
via four **distinct** multiples — market cap over annualized **fees** (gross
throughput), **revenue** (protocol take), **holders-revenue** (accrual to holders), and
**Mcap/TVL** (capital efficiency). Each measurable multiple is normalized to a
**relative attractiveness** (lower multiple = cheaper), blended into a `valuation_score`
labeled `cheap`/`fair`/`expensive` — a *relative* reading against documented heuristic
baselines, **not** an intrinsic/fair-value claim. `valuation_score` is `null` unless a
multiple was measurable; completeness is kept separate. Served read-only via
`/valuations`. Critically, the Alpha `valuation` component **graduated** from
`not_implemented` to consuming this score — so for assets with valuation data
`model_completeness` rises to ~0.95, **with no change to the Alpha formula, ranking, or
the three-output contract** (the ADR-006 promise, cashed in). Only **Technical Setup**
remains unimplemented.

<details><summary>Previous: Sprint 07 — Alpha Scoring Engine</summary>


The components are combined into the system's headline output — as **three separate
outputs**, never one number (§10): an **Alpha Score** (weighted blend of the
attractiveness components), a **Risk Score** carried through and shown **alongside**
(never folded in), and a **Confidence** (how much to trust the Alpha Score). Ranking is
by Alpha Score (ties broken toward higher completeness); a high Alpha with elevated Risk
or low Confidence is **down-classified** — no blind BUY. Served read-only via `/scores`.

</details>

<details><summary>Previous: Sprint 06 — Tokenomics & Risk Engine</summary>


On top of divergence, two assessments that separate "there is a divergence" from
"this is a real opportunity": **Token Value Capture** (does protocol strength accrue
to the token — dilution/float and whether fees/revenue reach holders) and a
**separate Risk Score** (liquidity, volatility, dilution, size; holder concentration
surfaced as an unavailable data gap). Both run over the Scanner's candidates, are
explainable, keep component values distinct from scores and `data_quality` separate,
and are served read-only via `/tokenomics` and `/risk`. They are **components/outputs
feeding the Alpha Score** (Sprint 07). No BUY language; missing data is explicit,
never `0`.

</details>

<details><summary>Previous: Sprint 05.1 — Economic Divergence Engine (refined)</summary>


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

</details>

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
  (measurement separate from interpretation, ADR-005).
- **Tokenomics (Token Value Capture)** — dilution/float + fee-to-holders value
  capture into a `value_capture_score` component; and a **separate Risk Engine** —
  liquidity/volatility/dilution/size into a `risk_score` + band (concentration
  surfaced as unavailable). Both persist runs with evidence.
- **Valuation Engine** — relative cheapness vs the economics generated, from four
  distinct multiples (MC over annualized fees / revenue / holders-revenue, and
  Mcap/TVL) into a `valuation_score` + label; `null` unless measurable; a component
  feeding Alpha (`valuation_runs` / `valuation_assessments`), served via `/valuations`.
- **Alpha Scoring Engine** — combines the components into **three separate outputs**
  (Alpha Score, Risk Score, Confidence) with a decision `status` and per-component
  breakdown; the not-yet-built component (Technical Setup) is renormalized out and
  reflected in Confidence, never zero-filled (ADR-006). Persists runs
  (`alpha_runs` / `alpha_scores`) with evidence; served via `/scores`.
- **Ingestion + analysis commands** — `scripts/ingest_market_data.py`,
  `scripts/ingest_fundamentals.py`, `scripts/run_scan.py`,
  `scripts/run_divergence.py`, `scripts/run_tokenomics.py`, `scripts/run_risk.py`,
  `scripts/run_valuation.py`, `scripts/run_alpha.py`.
- **Read API** — `/health`, `/assets`, `/market-data`, `/fundamentals`,
  `/opportunities`, `/scans`, `/divergences`, `/divergence-runs`, `/tokenomics`,
  `/tokenomics-runs`, `/risk`, `/risk-runs`, `/valuations`, `/valuation-runs`,
  `/scores`, `/score-runs` (plus the `/{id}` variants).
- Test suite under pytest (config, health, data-quality, migration, providers,
  normalization, ingestion services, scanner, divergence, tokenomics, risk, valuation,
  alpha, API) plus the foundation gate.

### Known limitations
- **Technical Setup is the only unimplemented Alpha component** (weight 5) — it is
  renormalized out and its absence caps Confidence (`model_completeness` ≤ 0.95) until
  it lands (a later sprint); it will then slot in with no scoring rewrite (ADR-006).
- **Valuation is coarse and absolute** — market-cap multiples against documented
  heuristic references, not DCF, peer/sector-relative, or historical-percentile
  valuation; the score is *relative cheapness*, never an intrinsic/fair-value claim.
- Divergence relies on **Track A** (single-snapshot growth windows) until history
  accumulates; **Track B** engages automatically per asset as history builds. A
  scheduler for automated ingestion cadence is deferred to Sprint 12.
- Tokenomics/Risk use available data only: dilution is a supply-ratio proxy, and
  **holder concentration is unavailable** (no on-chain provider yet) — surfaced as a
  gap, never guessed.
- Fundamentals cover only assets already in the market universe (Phase 1 `gecko_id`
  match; unmatched protocols skipped).
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

# assess token value capture and risk over the candidates:
docker compose exec app python scripts/run_tokenomics.py
docker compose exec app python scripts/run_risk.py
curl "http://localhost:8000/tokenomics"
curl "http://localhost:8000/risk?band=elevated"

# assess relative valuation over the candidates:
docker compose exec app python scripts/run_valuation.py
curl "http://localhost:8000/valuations?label=cheap"

# combine into the Alpha Score (+ Risk + Confidence), then read the ranked list:
docker compose exec app python scripts/run_alpha.py
curl "http://localhost:8000/scores"
curl "http://localhost:8000/scores?status=high_interest"
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
uv run python scripts/run_tokenomics.py                  # value capture
uv run python scripts/run_risk.py                        # risk (separate output)
uv run python scripts/run_valuation.py                   # relative valuation
uv run python scripts/run_alpha.py                       # Alpha + Risk + Confidence
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
