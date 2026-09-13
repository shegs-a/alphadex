# Sprint 06 Plan — Tokenomics & Risk Engine

## Objective

Add two distinct assessments that sit between "there is a divergence" and "this is a
real opportunity":

1. **Token Value Capture (Tokenomics).** Does protocol strength actually accrue to
   the *token*? Measure dilution/supply overhang and whether fees/revenue reach
   holders — turning divergence's coarse multiple into a real signal (distinction #2,
   §1).
2. **Risk Engine.** A **separate** Risk Score (§10) — liquidity, volatility,
   dilution, size, and data-quality risk — because a strong divergence with
   unacceptable risk is *not* a top candidate.

Both run on the Scanner's candidates, are configurable and explainable, persist their
results with evidence, and are served read-only via `/tokenomics` and `/risk`. They
are **components/outputs feeding Sprint 07's Alpha Scoring** — not the Alpha Score.

## Problem being solved

Divergence (Sprint 05) tells us a protocol may be improving faster than price
reflects. But two things can still make that a bad idea: the token may not capture
the protocol's economics (emissions/dilution, no fee accrual), or the asset may be
too risky (illiquid, volatile, heavy unlock overhang). AGENTS.md refuses to conflate
"a protocol getting stronger" with "the token benefiting" (#1 vs #2), and insists
Risk is a separate output from Alpha (§10). This sprint builds exactly those two
assessments so Sprint 07 can combine divergence + value capture, and report Risk
separately.

## Scope

- **Tokenomics module** (`src/alphadex/tokenomics/`)
  - `signals.py` — pure functions over an asset's latest observations:
    **float ratio** (`market_cap / FDV`, or `circulating / max|total supply`) as an
    inverse dilution-overhang measure; **value capture** (`revenue/fees`,
    `holders_revenue/revenue`, and a **real-yield** proxy
    `annualized holders_revenue / market_cap`). Each returns the value **and** how it
    was derived; a missing input is explicit `NOT_AVAILABLE`, never `0`.
  - `score.py` — a configurable **Token Value Capture score** (a component, not the
    Alpha Score) blending float ratio and value capture, with a completeness figure;
    missing inputs lower completeness and never inflate the score.
  - `service.py` + `repository.py` — run over candidates, persist a run + per-asset
    signals with evidence.
- **Risk module** (`src/alphadex/risk/`)
  - `factors.py` — pure risk factors (each 0..1, higher = riskier, with evidence):
    **liquidity** (low `volume/market_cap` turnover), **volatility** (magnitude of
    price change over 7d/30d), **dilution** (FDV overhang), **size** (small market
    cap). **Concentration/holder risk is `NOT_AVAILABLE`** (no on-chain provider yet)
    — surfaced as a data gap, never guessed.
  - `score.py` — a configurable **Risk Score** (0..1) + a **risk band**
    (`low` / `moderate` / `elevated` / `high`) over the available factors, with a
    data-quality figure. Poor data raises uncertainty, not a false low risk.
  - `service.py` + `repository.py` — run over candidates, persist a run + per-asset
    assessments with evidence.
- **Persistence** (migration `0006`, additive/reversible)
  - `tokenomics_runs` + `tokenomics_signals` (float ratio, value-capture components,
    `value_capture_score` nullable, `data_completeness`, `evidence` JSON).
  - `risk_runs` + `risk_assessments` (per-factor values, `risk_score` nullable,
    `risk_band`, `data_quality`, `evidence` JSON).
  - Typed decision fields; JSON only for the human-readable breakdown (§9). Missing
    scores are `NULL` with a status/band, never `0` (ADR-003). Config snapshotted on
    each run.
- **Read API** — `GET /tokenomics`, `GET /tokenomics/{asset_id}`,
  `GET /risk`, `GET /risk/{asset_id}`, `GET /tokenomics-runs`, `GET /risk-runs`.
- **Commands** — `scripts/run_tokenomics.py`, `scripts/run_risk.py`.
- **Config** — tokenomics and risk weights/thresholds and analysis scope, validated
  (weights sum to 1.0); never hard-coded (§2, §10).
- **Tests** — signals/factors (incl. explicit missing-data and no-inflation), scores
  (weights, bands, completeness), services (persist/rank/scope/isolation/history),
  API (evidence, filters, `404`, **no blind BUY language**), config validation. Keep
  all prior suites + the foundation gate green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (new entities), `docs/api/`.

## Out of scope

- **Alpha Scoring / Confidence** (Sprint 07). This sprint produces the Risk Score
  output and the Token Value Capture component; combining them into the Alpha Score
  (and computing Confidence) is next.
- **On-chain data** (holder concentration, whale wallets, unlock schedules by date).
  Concentration risk is marked `NOT_AVAILABLE` until an on-chain provider is added
  (a future sprint); no new provider integration here.
- Technical setup (Sprint 08), reporting, notifications, dashboard, scheduler.
- Precise emission/vesting schedules (need on-chain/tokenomics feeds); this sprint
  uses supply ratios (circulating/total/max, FDV) as the available dilution proxy.
- **The Divergence Engine and its classification semantics are a fixed contract**
  (ADR-005 / Sprint 05.1). This sprint *consumes* divergence signals as inputs but
  does **not** modify the divergence measurement, classifications, thresholds, or
  ranking. It mirrors ADR-005's discipline (component values distinct from scores;
  `data_completeness`/`data_quality` kept separate, never multiplied into a score;
  missing → explicit `NOT_AVAILABLE`) in the new Tokenomics and Risk modules.

## Decisions carried in (from the plan review)

- **Concentration/on-chain risk: deferred.** Concentration is `NOT_AVAILABLE`; no
  on-chain provider is integrated this sprint (recommended option).
- **Delivered as one sprint** (Tokenomics + Risk together), not split into 06a/06b —
  both are moderate, share the analytical pattern, and read existing data.

## Architecture impact

Adds two analytical modules (**Tokenomics** and **Risk** from the §2 boundary list),
following the established pattern (config-driven, explainable, persisted with
evidence, run over candidates). Both depend only on the internal data model. Given
this is the fourth and fifth engine of the same shape, a small **shared analytical
base** (run record + per-asset SAVEPOINT isolation + summary) will be extracted to
remove the duplication accumulating across Scanner/Divergence/Tokenomics/Risk
(recorded as debt in Sprint 05). Modular monolith preserved (ADR-001).

## Data impact

- **New (migration `0006`, additive):** `tokenomics_runs`, `tokenomics_signals`,
  `risk_runs`, `risk_assessments` (see Scope). Scores are nullable with an explicit
  status/band when unavailable — never `0` (ADR-003). Config snapshotted per run for
  reproducibility (§10).
- **Reused unchanged:** `assets`, `metric_observations` (market supply/FDV +
  fundamentals fees/revenue/holders-revenue), `scan_*` (candidate selection). New
  results are **derived data**, regenerable by re-running.
- **Metric distinctions preserved (§9):** value capture reads Fees, Revenue, and
  Holders Revenue as *distinct* inputs (`revenue/fees`, `holders_revenue/revenue`) —
  never collapsing them. Supply figures (circulating/total/max, FDV) drive dilution.

## API impact

- `GET /tokenomics` — per-candidate Token Value Capture signals (float ratio, value
  capture, real-yield proxy, score, completeness, evidence).
- `GET /risk` — per-candidate Risk assessments (factor breakdown, risk score, risk
  band, data-quality, evidence). Language uses *risk elevated / risk high*, never
  BUY/GUARANTEED (§10).
- `GET /tokenomics/{id}`, `GET /risk/{id}` — one asset's latest (404 if not
  assessed); `GET /tokenomics-runs`, `GET /risk-runs` — run history. Prior endpoints
  unchanged.

## UI impact

None (dashboard deferred to Sprint 10).

## Implementation tasks

1. Shared analytical base (extract the run/isolation/summary pattern).
2. `tokenomics/{signals,score,service,repository}.py`.
3. `risk/{factors,score,service,repository}.py`.
4. Migration `0006` — the four tables; verify up/down.
5. `api/routes/{tokenomics,risk}.py`; register routers.
6. `scripts/run_tokenomics.py`, `scripts/run_risk.py`.
7. `config.py` + `.env.example` — tokenomics + risk weights/thresholds/scope.
8. Tests (signals/factors, scores, services, API, config); keep prior suites +
   foundation gate green.
9. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
10. Verify end-to-end on Docker + PostgreSQL: ingest, scan, then run tokenomics and
    risk; confirm `/tokenomics` and `/risk` return explainable results with missing
    inputs (e.g. holders-revenue, concentration) surfaced honestly, never zeroed.

## Testing strategy

- **Unit — tokenomics signals:** float ratio from supply/FDV is correct; value
  capture uses Fees/Revenue/Holders-Revenue distinctly; a token with fees but no
  holders-revenue yields a `NOT_AVAILABLE` value-capture component (not `0`) and a
  lower completeness.
- **Unit — risk factors:** each factor computes as expected at its thresholds; a
  missing input drops that factor and lowers data-quality (never a false low risk);
  concentration is always `NOT_AVAILABLE`.
- **Unit — scores:** Token Value Capture and Risk scores are deterministic functions
  of the configured weights; bands map correctly; missing inputs never inflate a
  favorable score.
- **Integration — services (SQLite):** seeded observations + a scan produce runs and
  per-asset rows for the candidates; per-asset failure isolated; scope honored;
  re-running keeps history.
- **API:** `/tokenomics` and `/risk` return the documented shapes with evidence;
  filters and `404` work; a serialized-output scan asserts no forbidden BUY terms.
- **Config:** weights validated; invalid config rejected clearly.
- Deterministic; SQLite for portable runs, PostgreSQL via Docker. Foundation gate
  stays green.

## Acceptance criteria

- `uv run pytest` passes (new + prior suites); the foundation gate still passes.
- `alembic upgrade head` applies `0006` (and `downgrade` reverses it), creating the
  four new tables.
- Tokenomics and Risk results are computed and persisted with typed components, a
  score (or explicit `NULL` + status/band when unavailable — never `0`), a
  completeness/data-quality figure, and full evidence; distinct Fees/Revenue/Holders
  Revenue usage is preserved (§9).
- Risk is a **separate** output (its own tables/endpoint), not folded into any Alpha
  score. Concentration risk is surfaced as `NOT_AVAILABLE`.
- `GET /tokenomics` and `GET /risk` return explainable results; **no BUY/GUARANTEED
  language** anywhere.
- Engines depend only on the internal data model. `ruff` clean, `mypy` clean; no
  out-of-scope work (alpha scoring, on-chain providers) introduced.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` updated; Sprint 06 report
  completed.
- Release gate (AGENTS.md §7): tests pass → Docker builds → app starts →
  migrations apply → ingest + scan + tokenomics + risk + read workflow works → docs
  updated → release commit → tag `v0.6.0` at the release head.

## Risks

- **Two engines in one sprint (size).** Mitigation: both share the established
  pattern and produce component scores from existing data; the shared base reduces
  new code. If it grows too large, split into 06a Tokenomics / 06b Risk (§15).
- **No on-chain data → incomplete risk/tokenomics.** Mitigation: concentration and
  precise unlock schedules are `NOT_AVAILABLE`; data-quality reflects the gap; never
  fabricate. An on-chain provider is a future sprint.
- **Missing data treated as `0`** (would understate risk or overstate value capture).
  Mitigation: explicit `NOT_AVAILABLE`, renormalized weights over present inputs,
  dedicated tests asserting no inflation and no false-low-risk.
- **Proxy naivety** (volatility from price-change windows; dilution from static
  supply ratios). Mitigation: label as proxies in evidence; refine with history and
  on-chain data later.
- **Scope creep into Alpha Scoring.** Mitigation: Risk Score and Value Capture are
  emitted as separate outputs; combining is Sprint 07.

## Rollback considerations

Migration `0006` is additive with a working `downgrade()`: `alembic downgrade -1`
drops the four new tables (Sprints 01–05 schema untouched). The results are
**derived data**, regenerable by re-running the engines, so dropping them loses no
source information. Both engines are read-only over existing observations/scan
results, so ingestion, scan, divergence, and read paths are unaffected.
`git checkout v0.5.0` returns to the Divergence foundation; `v0.5.0` remains the
prior stable anchor and `v0.6.0` becomes the next once tagged.
