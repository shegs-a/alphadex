# Sprint 07 Report — Alpha Scoring Engine

## Sprint objective

Combine the components built in Sprints 02–06 into the system's headline
decision-support output — as **three separate outputs**, never one number (AGENTS.md
§10): an **Alpha Score** (attractiveness), a **Risk Score** (surfaced alongside, not
folded in), and a **Confidence** (how much to trust the Alpha Score). Rank by Alpha
Score, classify an overall decision `status` in the allowed vocabulary (never BUY), and
persist it all with evidence. See ADR-006.

## What shipped

- **`alpha` module** (`src/alphadex/alpha/`):
  - `components.py` — seven pure adapters, each turning an upstream output into a
    normalized attractiveness contribution in [0,1] **and** reporting availability
    (missing → unavailable, never `0`): economic growth (fundamentals trend),
    divergence (from the ADR-005 **classification**, not the raw gap), token value
    capture (Sprint 06 `value_capture_score`), market strength (momentum + turnover),
    tokenomics (`float_ratio`). Valuation and technical_setup report "not implemented".
  - `score.py` — the Alpha Score (weighted average, renormalized over available
    components), Confidence (`model_completeness` blended with upstream data quality),
    alpha/confidence bands, a completeness-aware rank key, and the decision `status`.
  - `service.py` + `repository.py` — read each asset's latest divergence signal,
    tokenomics signal, risk assessment, and market observations; per-asset SAVEPOINT
    isolation; a run record; rank by Alpha Score with completeness as tie-break.
- **Migration `0007`** (additive/reversible) — `alpha_runs`, `alpha_scores`. Alpha,
  Risk, and Confidence are **distinct columns**, plus `model_completeness`, `status`,
  `rank`, a `components` JSON breakdown, and `evidence` JSON. Nullable scores are
  `NULL` with a status, never `0`.
- **Read API** — `GET /scores` (ranked; filter by `status`/`risk_band`/
  `confidence_band`), `GET /scores/{asset_id}`, `GET /score-runs`.
- **Command** — `scripts/run_alpha.py`.
- **Config** — the full 7-component Alpha weight vector (AGENTS.md defaults, validated
  to sum to 1.0), confidence blend + bands, decision-status thresholds, references;
  documented in `.env.example`. Not fitted to any known outcomes (§10).
- **ADR-006** + updated README, CHANGELOG, `docs/data`, `docs/api`.

## Key design decisions (and the guarantees requested)

**1. Renormalization must not inflate Alpha — enforced as an invariant, not just a
test.** The Alpha Score is a weighted **average** of the available contributions
(`Σ wᵢvᵢ / Σ wᵢ` over available `i`), so it is bounded by their min and max. A missing
component can never push Alpha above what the present evidence supports. Tests assert
the score stays within `[min, max]` of the available contributions, and that dropping a
genuinely-high component *lowers* the shorter asset rather than inflating it.

**2. The three outputs stay independent.** Alpha ranks; Risk and Confidence are
surfaced alongside. Neither Risk nor Confidence enters the Alpha formula — they
down-classify `status` and (completeness) break rank ties only.

**3. Missing data buys no ranking advantage.** Ranking is by Alpha Score with
`model_completeness` breaking ties **toward** the more-complete asset. Test: an asset
with all 7 components (its 5 shared values identical to a 5-component asset, the extras
set neutral) **ties** on Alpha but ranks **above** the shorter asset — renormalization
is a normalization, not a bonus. A shorter set only out-ranks a complete one when the
complete asset's extra evidence is genuinely weak (true signal; the shorter asset's
lower Confidence flags the uncertainty).

**4. Confidence is a real analytical output, not a disclaimer.** With 5/7 components
available, `model_completeness` caps at 0.80 and visibly constrains Confidence. When
Valuation and Technical Setup land, Confidence rises with **no scoring rewrite** — the
full target vector already lives in config. Test: identical available evidence →
identical Alpha, and Confidence differs *only* when the data-quality inputs differ.

**5. Divergence feeds Alpha via its classification, not the raw gap** — so
repricing/momentum don't score as opportunity (no VVV trap) and price momentum is not
double-counted (it lives only in the small, separate `market_strength` component).

## Handling of the two unimplemented components

Valuation (weight 15) and Technical Setup (weight 5) — 20% of the intended model — are
treated exactly like any missing input (ADR-003/ADR-006): renormalized out of the Alpha
Score and reflected in Confidence via `model_completeness`, **never zero-filled**. The
`components` breakdown records them as `available: false` with detail `not_implemented`,
distinct from a per-asset data gap.

## Verification

- **179 tests pass** (148 prior + 31 new alpha tests: components, score/renormalization,
  the no-inflation invariant, both ranking scenarios, confidence, status
  down-classification, service isolation, and API). ruff + format clean; mypy clean
  (64 source files); foundation gate 7 passed.
- Migration `0007` applies and reverses (`test_migration` covers `alpha_runs` /
  `alpha_scores` up and down).
- End-to-end on Docker + PostgreSQL 16: `docker compose up --build`, `/health` at
  0.7.0, full pipeline ingest → scan → divergence → tokenomics → risk → **alpha**, and
  `/scores` returns the three separate outputs with `model_completeness < 1.0`
  reflecting the two unimplemented components, and no BUY language.

## Deviations from the plan

None material. The `.env.example` already carried commented `ALPHA_WEIGHT_*`
placeholders from an earlier sprint; they were expanded into the full documented set
(references, confidence blend, bands, thresholds).

## Deferred (out of scope, as planned)

A real **Valuation engine** and the **Technical Setup engine** (Sprint 08);
reporting/notifications (09); dashboard (10); backtesting and any outcome-based weight
tuning (11); scheduler (12). On-chain holder concentration and unlock schedules remain
surfaced data gaps.

## Rollback

Migration `0007` is additive with a working `downgrade()` — `alembic downgrade -1`
drops `alpha_runs` / `alpha_scores` (Sprints 01–06 schema untouched). Alpha scores are
derived data, regenerable by re-running `scripts/run_alpha.py`. `git checkout v0.6.1`
returns to the Tokenomics/Risk foundation; `v0.6.1` remains the prior stable anchor.

## Release

`v0.7.0` — release commit on `claude/resume-session-devices-ibdww4`; annotated tag
pushed; GitHub Release published.
