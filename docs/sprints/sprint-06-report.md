# Sprint 06 Report — Tokenomics & Risk Engine

## Sprint objective

Add two distinct assessments between "there is a divergence" and "this is a real
opportunity": **Token Value Capture** (does protocol strength accrue to the token?)
and a **separate Risk Score** (§10). Both run over the Scanner's candidates, are
configurable and explainable, persist results with evidence, and feed Sprint 07's
Alpha Score — they are not the Alpha Score.

## Completed tasks

- **Shared analytical base** (`src/alphadex/analysis/base.py`): candidate selection
  (tiered pipeline, §9), latest-value loading (present values only, never `0`), and a
  per-asset SAVEPOINT `run_isolated` helper (§8). Used by both new engines.
- **Tokenomics** (`src/alphadex/tokenomics/`): `signals` (float ratio,
  revenue/fees, holders/revenue, real-yield — Fees ≠ Revenue ≠ Holders Revenue, §9,
  each `None` when missing); `score` (a `value_capture_score` blending dilution and
  value capture over present components, with a separate `data_completeness`, and a
  `value_capture_label` that is `unknown` when no value-capture input exists — a
  strong float ratio alone does not prove value capture); `service`; `repository`.
- **Risk** (`src/alphadex/risk/`): `factors` (liquidity, volatility, dilution, size;
  concentration always `NOT_AVAILABLE`); `score` (a separate `risk_score` + band over
  available factors, `data_quality` kept separate — never a false low risk);
  `service`; `repository`.
- **Persistence** (migration `0006`, additive/reversible): `tokenomics_runs`/
  `tokenomics_signals` and `risk_runs`/`risk_assessments`. Results are derived data.
- **API**: read-only `GET /tokenomics`, `/tokenomics/{id}`, `/tokenomics-runs`,
  `GET /risk`, `/risk/{id}`, `/risk-runs`.
- **Ops**: `scripts/run_tokenomics.py`, `scripts/run_risk.py`.
- **Config**: tokenomics + risk weights/refs/scope/bands (weights validated to 1.0).
- **Tests** (+24): tokenomics (config, signals, score, service, API), risk (config,
  factors, score, service, API), migration extended for `0006`.
- **Docs**: README, CHANGELOG (`0.6.0`), `docs/data`, `docs/api`, this report.

## Incomplete tasks

None within scope. The Alpha Score / Confidence trio (07), on-chain concentration,
and precise unlock schedules are deferred as planned.

## Database changes

Migration `0006` (additive, on top of `0005`): `tokenomics_runs`,
`tokenomics_signals`, `risk_runs`, `risk_assessments`. Sprints 01–05 schema
untouched. Results are derived data (regenerable by re-running).

## API changes

Added read-only `GET /tokenomics`, `/tokenomics/{id}`, `/tokenomics-runs`,
`GET /risk`, `/risk/{id}`, `/risk-runs`. Prior endpoints unchanged.

## Tests executed

```
uv run pytest                 # 145 passed
uv run ruff check .           # clean
uv run ruff format --check .  # clean
uv run mypy src               # success (57 source files)
python3 -m unittest tests.test_foundation   # 7 passed
docker compose up --build     # PostgreSQL 16
docker compose exec app python scripts/run_tokenomics.py
docker compose exec app python scripts/run_risk.py
```

## Test results

- **pytest: 145 passed** (121 prior + 24 new). ruff + format clean; mypy success
  (57 files); foundation gate 7 passed.
- **End-to-end (Docker + PostgreSQL 16):** migration `0006` applied; tokenomics and
  risk each ran over the scan's **91** candidates, 0 failed. `/risk` produced a
  spread of bands (12 low / 65 moderate / 14 elevated) with `concentration_risk`
  always `null` (surfaced gap) and per-factor drivers in evidence. `/tokenomics`
  scored assets with fee/revenue data (e.g. SOL, AAVE) with distinct
  `revenue_to_fees`/`real_yield`, while assets with only a float ratio (ETH, BNB,
  stablecoins) are labeled `unknown` — not "strong".

## Bugs discovered / fixed

- **Tokenomics label over-claimed on thin data (found in live verification, fixed
  before release):** an asset with a perfect float ratio but no fee/revenue/holders
  data scored 1.0 and was labeled `strong` value capture despite value capture being
  entirely unmeasured (completeness 0.25). Corrected so the label is `unknown` when
  no value-capture input is present (the score still records the dilution
  measurement). This applies ADR-005's "poor data must not masquerade as a strong
  signal" to Tokenomics; the divergence engine was **not** modified.

## Known limitations

- **No on-chain data:** holder concentration is `NOT_AVAILABLE`; dilution is a
  supply-ratio proxy (no precise unlock schedules). Surfaced as gaps, never guessed.
- **Proxy naivety:** volatility from price-change magnitude; risk-band cut points and
  normalization references are documented heuristics, tunable via config.
- Components only — no Alpha/Risk/Confidence combination yet (Sprint 07). Synchronous
  access; candidates-only scope by default (tiered pipeline).

## Technical debt

- The existing Scanner/Divergence services still carry their own run/isolation code;
  they can migrate to `alphadex.analysis.base` later (the new engines already use it).
- Risk-band thresholds and weights are un-tuned defaults (deliberate — no hindsight
  bias); revisit with backtesting (Sprint 11).

## Deviations from the plan

- Added the tokenomics `unknown`-label honesty fix (see Bugs) — a small in-scope
  correction surfaced during verification, consistent with ADR-005.

## Architecture decisions

No new ADRs. Adds the Tokenomics and Risk modules (§2) plus a shared analytical base.
Honors ADR-003 (missing → explicit, never `0`), §9 (Fees/Revenue/Holders Revenue
distinct), §10 (Risk a separate output; no blind BUY; configurable weights), and the
ADR-005 discipline (component values distinct from scores; data quality separate).
The divergence contract (ADR-005) was consumed, not modified.

## Release/version created

- Version **v0.6.0**; release commit on `claude/resume-session-devices-ibdww4`;
  annotated tag `v0.6.0` (pushed; GitHub Release published).

## Rollback procedure

- `alembic downgrade -1` drops the four Sprint 06 tables (derived data; nothing
  source lost). Both engines are read-only over existing observations/scan results,
  so ingestion, scan, divergence, and read paths are unaffected.
- `git checkout v0.5.1` returns to the divergence foundation. `v0.5.1` remains the
  prior stable anchor; `v0.6.0` becomes the new one.

## Recommended next steps (Sprint 07 — Alpha Scoring Engine)

1. Combine the components into the **Alpha Score** (configurable weights: economic
   growth, divergence, valuation, token value capture, market strength, tokenomics,
   technical) — three separate outputs: **Alpha Score, Risk Score, Confidence**.
2. Compute **Confidence** from data completeness/quality, freshness, signal
   agreement, and divergence strength (finally giving data quality a home in ranking).
3. Rank opportunities by Alpha Score with Risk and Confidence shown separately; keep
   every output explainable; no blind BUY (§10).
