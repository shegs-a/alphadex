# Changelog

All notable changes to AlphaDex Scout are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Work toward the next release. Move entries under a version heading on release._

## [0.7.0] — 2026-09-13

### Added
- **Alpha Scoring Engine (Sprint 07)** — the system's headline decision-support
  output, produced as **three separate outputs**, never one number (§10, ADR-006):
  - **Alpha Score** — a configurable weighted blend of the *attractiveness*
    components (economic growth, divergence, token value capture, market strength,
    tokenomics), with an `alpha_band`.
  - **Risk Score** (+ band) — carried through from the Sprint 06 Risk engine and
    surfaced **alongside** Alpha, never folded into it.
  - **Confidence** (+ band) — how much to trust the Alpha Score, from
    `model_completeness` and upstream data quality.
  - A **decision `status`** in the allowed vocabulary only — `high_interest`,
    `potential_opportunity`, `watch`, `risk_elevated`, `low_confidence`,
    `thesis_weakening`, `insufficient_data`. Never BUY/GUARANTEED. A high Alpha with
    elevated Risk or low Confidence is down-classified.
- New `alpha_runs` / `alpha_scores` tables (migration `0007`, additive/reversible);
  Alpha, Risk, and Confidence are distinct columns, plus `model_completeness`, a
  per-component `components` breakdown, and `evidence`. Read API: `GET /scores`
  (ranked by Alpha Score; Risk + Confidence shown separately; filter by
  status/band), `GET /scores/{asset_id}`, `GET /score-runs`. New `scripts/run_alpha.py`.
- **ADR-006** — records the three-output model and the renormalize-and-reflect-in-
  Confidence handling of not-yet-implemented components.

### Notes
- **Valuation (15) and Technical Setup (5) are not implemented yet.** Their 20% of the
  intended weight is handled like any missing input: weights are **renormalized** over
  the available components and the absence is reflected in **Confidence**
  (`model_completeness` caps at 0.80) — **never zero-filled** (ADR-003). The full
  7-component target vector lives in config so the intended model is explicit; the two
  components slot in automatically when built (Sprint 08+).
- The Alpha Score is a weighted **average** of available contributions, so it is
  bounded by their min/max — a missing component can never inflate it. Ranking is by
  Alpha Score with `model_completeness` breaking ties **toward** the more-complete
  asset, so renormalizing a shorter component set never buys a rank advantage.
- Divergence feeds Alpha via its ADR-005 **classification** (not the raw gap), so
  repricing/momentum do not score as opportunity and price is not double-counted.
- Default weights are the documented AGENTS.md defaults — **not** fitted to any known
  outcomes (no hindsight bias, §10). Full suite: 179 tests; ruff and mypy clean.

## [0.6.1] — 2026-09-13

### Fixed
- Tokenomics & Risk validation (Sprint 06.1):
  - **`value_capture_score` no longer reads as "strong" from dilution alone.** It
    blended dilution (`float_ratio`) and value capture over *present* components, so a
    dilution-only asset (e.g. ETH/stablecoins: `float_ratio = 1.0`, no fee/revenue
    data) scored `1.0` while labeled `unknown`, and ranked #1. The score is now
    `null` unless value capture was actually measured; `float_ratio` remains exposed
    separately, and such assets are no longer ranked in tokenomics. Prefers explicit
    `null`/status over a sentinel number (ADR-003/ADR-005 discipline).

### Changed
- Documented unambiguous semantics for every Sprint 06 output: risk factors are
  absolute values clamped to [0,1] against a configured reference (what `1.0` means
  per factor is now documented in `docs/data`); genuine zeros (e.g. `revenue = 0` →
  `revenue_to_fees = 0.0`) are preserved and distinct from `null` (missing) and from a
  zero denominator (undefined → `null`). Ranking semantics clarified in `docs/api`
  (tokenomics = value-capture measurement; risk = highest risk first, a warning
  ordering — neither is an opportunity ranking).

### Notes
- Source-only change (no migration; `value_capture_score` already nullable);
  tokenomics results are derived data and repopulate on re-run. Divergence (ADR-005)
  untouched. Verified end-to-end on Docker + PostgreSQL 16 — after re-running, ETH and
  other 100%-float assets show `value_capture_score: null` / `unknown` and are
  unranked. Full suite: 148 tests; ruff and mypy clean.

## [0.6.0] — 2026-09-13

### Added
- Tokenomics & Risk engines (Sprint 06) — two distinct assessments over the
  Scanner's candidates, both components/outputs feeding Sprint 07's Alpha Score:
  - **Token Value Capture (Tokenomics):** a `value_capture_score` (a component, not
    the Alpha Score) blending dilution/float overhang (`market_cap/FDV`, or
    `circulating/max|total` supply) with value capture — `revenue/fees`,
    `holders_revenue/revenue`, and a real-yield proxy (annualized holders-revenue /
    market cap). Fees ≠ Revenue ≠ Holders Revenue kept distinct (§9). Component
    ratios are stored separately from the score; `data_completeness` is separate;
    missing inputs are `NOT_AVAILABLE`, never `0`. Read-only `GET /tokenomics`,
    `/tokenomics/{id}`, `/tokenomics-runs`; `scripts/run_tokenomics.py`.
  - **Risk Engine:** a **separate** `risk_score` (§10) + `risk_band`
    (`low`/`moderate`/`elevated`/`high`/`unknown`) over distinct factors — liquidity
    (turnover), volatility (price-change magnitude), dilution (FDV overhang), size —
    with `data_quality` kept separate from the score. **Holder concentration is
    `NOT_AVAILABLE`** (no on-chain provider yet) — a surfaced data gap, never guessed.
    Read-only `GET /risk`, `/risk/{id}`, `/risk-runs`; `scripts/run_risk.py`.
  - New `alphadex.analysis` shared base (candidate selection, latest-value loading,
    per-asset SAVEPOINT isolation) used by both engines.
  - Migration `0006` (additive, reversible): `tokenomics_runs`/`tokenomics_signals`
    and `risk_runs`/`risk_assessments`. Results are derived data.
  - Config: tokenomics + risk weights/thresholds/scope (weights validated to 1.0).

### Notes
- Risk is deliberately a separate output — a strong divergence with unacceptable
  risk is not a top candidate. No changes to the divergence engine (ADR-005 contract
  consumed, not modified). Verified end-to-end on Docker + PostgreSQL 16. Full suite:
  145 tests; ruff and mypy clean.

## [0.5.1] — 2026-09-13

### Changed
- Divergence Engine refinement (Sprint 05.1) — distinguish genuine divergence from
  repricing/momentum (see `docs/decisions/ADR-005`):
  - **Measurement vs. interpretation are now separate.** The signed economic-price
    gap is a *measurement*; a positive gap no longer implies an opportunity.
  - **Semantic classifications** replace the single gap-sign test:
    `potential_mispricing`, `fundamental_divergence`, `fundamental_repricing`,
    `momentum`, `thesis_weakening`, `watch`, `insufficient_data`. Classification now
    reads the **price regime** (materiality floor, a stagnant/declining ceiling, and
    an "already repriced" marker) — configurable, documented heuristics, not a single
    hard-coded cutoff.
  - **Distinct measurement fields** added: `divergence_gap` (raw `ft − pt`),
    `signal_strength` (magnitude), and `valuation_level` (the multiple), alongside
    the existing trends/score/data-quality. No field is collapsed into another.
  - **Data quality stays separate from signal strength** — it is not multiplied into
    the score. Ranking remains a preliminary divergence-*measurement* ranking
    (largest measured gap), now documented as such in the API — not an opportunity
    ranking (that is the Alpha Score, Sprint 07).
  - **Evidence** language corrected: the 7d/30d comparison is described as "recent
    7-day fee run-rate ~X% vs the 30-day baseline" (not a proven long-term trend),
    with an explicit `evidence_strength` (LOW for single-snapshot growth-window).
  - Config: removed the unused `DIVERGENCE_WEAKENING_THRESHOLD`; added
    `DIVERGENCE_PRICE_STAGNANT_CEILING` and `DIVERGENCE_PRICE_STRONG_THRESHOLD`.

### Fixed
- **VVV was misclassified** as `fundamental_divergence` purely because its
  fundamental growth (+155.8%) exceeded its price growth (+98.3%), despite price
  having already risen +98%. It is now `fundamental_repricing`. A regression test
  pins this.

### Notes
- Migration `0005` (additive, reversible) adds the three measurement columns to
  `divergence_signals`. Verified end-to-end on Docker + PostgreSQL 16. Full suite:
  121 tests; ruff and mypy clean. No changes to the Alpha Score (Sprint 07) or to
  Sprint 06 scope.

## [0.5.0] — 2026-09-13

### Added
- Economic Divergence Engine (Sprint 05) — the heart of the thesis:
  - Detects where a protocol's fundamentals are improving faster than the market's
    price/valuation recognizes. A pure analytical layer over the internal data
    model; runs on the Scanner's candidates (tiered pipeline, §9).
  - **Two-track trend measurement** in one engine: **Track A** (provider 7d/30d
    growth windows — a fundamentals *acceleration* signal that works from a single
    snapshot) and **Track B** (cross-time change from the append-only history, keyed
    off `observed_at` — hindsight-free and preferred when available). A coarse
    market-cap-to-fees multiple is one additional input.
  - A signed **divergence score** in [-1, 1] (a component, **not** the Alpha Score),
    classification (`fundamental_divergence` / `watch` / `thesis_weakening` /
    `insufficient_data`), and full **explainable evidence** (what changed / why now /
    what supports / contradicts / invalidates / major risk) with an honest
    `data_quality` figure. A missing core input yields a `null` score with a
    classification — never `0` (ADR-003). No blind BUY language (§10).
  - Persistence: `divergence_runs` (config snapshot) and `divergence_signals`
    (typed trends/score/method/data_quality + a JSON evidence breakdown). Migration
    `0004` (additive, reversible); signals are derived data.
  - Read-only `GET /divergences` (ranked, filter by classification),
    `GET /divergences/{asset_id}` (404 if not analyzed), `GET /divergence-runs`.
  - `scripts/run_divergence.py` one-shot pass; scope/thresholds/weights/min-history
    configurable in `config.py` / `.env.example` (weights validated to sum to 1.0).

### Notes
- Divergence's value compounds as observation history accrues (Track B); automated
  ingestion cadence (a scheduler) is deferred to Sprint 12. Verified end-to-end on
  Docker + PostgreSQL 16: migration `0004` applies, a pass over the scan's 91
  candidates+watch produced 2 fundamental_divergence / 8 watch / 8 thesis_weakening
  / 73 insufficient_data, with caveated evidence. Full suite: 114 tests; ruff and
  mypy clean.

## [0.4.0] — 2026-09-13

### Added
- Opportunity Scanner (Sprint 04) — the first analytical pass:
  - A configurable, explainable **screen** over existing `market.*` and
    `fundamental.*` observations (fetches nothing external): inclusion **gates**
    (market-cap floor/ceiling, minimum 24h volume, data freshness) each returning
    pass/fail with the value and threshold considered, plus a **preliminary Screen
    Score** (log-scaled activity/liquidity/momentum blend, configurable weights).
    This is explicitly **not** the Alpha Score.
  - Per-asset classification: `candidate` / `watch` / `insufficient_data` /
    `excluded`. Candidates and watches are scored and ranked; excluded/insufficient
    carry a `null` score (never `0`). Missing inputs lower `data_completeness` and
    can never inflate a score (§10, ADR-003). No blind BUY language (§10).
  - Persistence: `scan_runs` (with a snapshot of the config used) and
    `scan_results` (typed decision fields + a JSON per-criterion evidence
    breakdown). Migration `0003` (additive, reversible).
  - Read-only `GET /opportunities` (ranked, filter by status),
    `GET /opportunities/{asset_id}` (404 if unscanned), `GET /scans`.
  - `scripts/run_scan.py` one-shot scanner; screen thresholds and weights
    configurable in `config.py` / `.env.example` (weights validated to sum to 1.0).

### Notes
- Scan results are derived data (regenerable by re-running a scan). Verified
  end-to-end on Docker + PostgreSQL 16: migration `0003` applies, a scan over 100
  assets produced 19 candidates / 72 watch / 9 excluded, and `/opportunities`
  returned ranked candidates with full gate + signal evidence (excluded assets
  scored `null`). Full suite: 89 tests; ruff and mypy clean.

## [0.3.0] — 2026-09-12

### Added
- Fundamental Intelligence (Sprint 03):
  - `FundamentalDataProvider` interface + `RawFundamentalSnapshot` DTO (reusing the
    provider error hierarchy) and a **DefiLlama** adapter assembling TVL, fees,
    revenue, and holders-revenue from `/protocols` and `/overview/fees` (joined by
    protocol slug, deduplicated by `gecko_id` keeping the largest-TVL
    representative). Provider factory extended.
  - Normalization into distinct `fundamental.*` metrics — `tvl_usd`, `fees_usd.*`,
    `revenue_usd.*`, `holders_revenue_usd.*` — with units, periods, and provenance.
    Fees ≠ Revenue ≠ Holders Revenue ≠ TVL are kept strictly distinct and never
    derived from one another; absent values are `NOT_AVAILABLE`, never `0`.
  - Ingestion service that matches protocols to assets **already in the universe**
    by `gecko_id` (Phase 1), skips and counts unmatched protocols, attaches a
    `defillama` source id to the matched asset, optionally fills an unknown asset
    category, isolates per-protocol failures (SAVEPOINT), and records an
    `ingestion_runs` row.
  - Read-only `GET /fundamentals` (latest `fundamental.*` observation per
    asset/metric/period, with `value_status`, provenance, and freshness).
  - `scripts/ingest_fundamentals.py` one-shot ingestion; DefiLlama configuration in
    `config.py` and `.env.example`.

### Changed
- `/market-data` is now scoped to the `market.*` namespace so it never returns
  `fundamental.*` observations (clean domain separation as the two domains share
  `metric_observations`).

### Notes
- No schema change — fundamentals reuse `metric_observations`, `asset_source_ids`,
  and `ingestion_runs`.
- Verified end-to-end on Docker + PostgreSQL 16 with live DefiLlama: 2,367
  protocols fetched, 35 matched to the top-100 market universe by `gecko_id`, 2,332
  skipped, 315 observations written; `/fundamentals` returned real fees/revenue/TVL
  with unreported metrics as `NOT_AVAILABLE`. Full suite: 63 tests; ruff and mypy
  clean.

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
