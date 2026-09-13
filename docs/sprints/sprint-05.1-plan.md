# Sprint 05.1 Plan — Divergence Engine Diagnostic & Refinement

## Objective

Refine the Sprint 05 Economic Divergence Engine so it distinguishes **genuine
economic–price divergence** from **fundamental repricing / momentum**. A positive
mathematical gap between fundamental growth and price growth is a *measurement*, not
an *opportunity interpretation*. The engine must separate the two.

This is a focused, reversible refinement — not Sprint 06, and not the Alpha Score.

## Diagnosis (current behavior, verified against the code)

Traced `raw observations → trends → gap → valuation → classification → evidence →
ranking` in `src/alphadex/divergence/`. Findings, confirmed against live VVV:

- **Classification** ([engine.py](../../src/alphadex/divergence/engine.py)) is only:
  `score >= threshold AND fundamentals_improving → fundamental_divergence`. It never
  checks whether **price has already risen strongly**, so a strongly-repriced asset
  is mislabeled as undiscovered divergence.
- **VVV** (`fundamentals_trend +155.8%`, `price_trend +98.3%`, `gap 0.575`) was
  classified `fundamental_divergence` purely because `1.558 > 0.983`, even though
  price already ran +98%. The contradiction was noted in evidence but had no effect
  on the label.
- **`valuation_multiple` (122.35×)** = `market_cap / annualized_fees_30d`. It is
  **evidence only**; the scoring input is `valuation_trend` (change over time), which
  is `null` without history. Confirmed not used in ranking.
- **`data_quality` (0.30)** = `completeness(0.5) × growth_window_factor(0.6)`. It is
  recorded but **does not affect ranking** (ranking sorts by `divergence_score`).
- **Ranking** is a pure `divergence_score` sort — a *measurement* ranking, but the
  API did not say so.

## Scope

- **Semantic classifications** (replace the single positive/negative test):
  `potential_mispricing`, `fundamental_divergence`, `fundamental_repricing`,
  `momentum`, `thesis_weakening`, `watch`, `insufficient_data`. Defined by
  fundamentals materiality and **price regime**, using configurable, documented
  heuristics (not one arbitrary hard-coded price cutoff).
- **Separate the concepts** (§10 of the spec): keep `divergence_score` (the signed
  measurement) and add `divergence_gap` (raw `ft − pt`), `signal_strength`
  (magnitude of the measurement, 0..1), and `valuation_level` (the multiple) as
  distinct fields alongside `fundamentals_trend`, `price_trend`, `valuation_trend`,
  `data_quality`, `classification`. **Do not** multiply score by data quality.
- **Ranking** stays a pure divergence-measurement ranking; **rename/document** it as
  such in the API and docs (rank = highest measured economic–price gap, NOT best
  opportunity). Data quality and valuation still do **not** influence ranking; that
  is deferred to the Alpha Score / Confidence (Sprint 07), documented explicitly.
- **Evidence** language: describe the 7d/30d comparison as "recent 7-day fee
  run-rate ~X% above the 30-day baseline" (not a proven long-term trend), and add an
  explicit **evidence strength** (LOW for single-snapshot growth-window).
- **Schema**: migration `0005` adds `signal_strength`, `divergence_gap`,
  `valuation_level` columns to `divergence_signals`.
- **Config**: remove the now-unused `divergence_weakening_threshold`; add
  `divergence_price_stagnant_ceiling` and `divergence_price_strong_threshold`
  (documented heuristics). Keep `divergence_threshold` as the minimum gap for a
  divergence-family classification.
- **ADR-005** recording the classification model (measurement vs interpretation).
- **Tests** for cases A–G (incl. a VVV regression), updated Sprint 05 tests where
  behavior is intentionally corrected, docs, and a `v0.5.1` release.

## Classification logic (heuristic, configurable)

Let `ft = fundamentals_trend`, `pt = price_trend`, `gap = ft − pt`.

```
improving  = ft >= min_fundamentals_improvement        (default 0.05)
declining  = ft <= -min_fundamentals_improvement
price_strong    = pt >= price_strong_threshold          (default 0.50)
price_flat_down = pt <= price_stagnant_ceiling          (default 0.05)

if not (ft and pt available):        insufficient_data
elif declining:                      thesis_weakening
elif price_strong:                   fundamental_repricing if improving else momentum
elif improving and gap >= threshold: potential_mispricing if price_flat_down
                                      else fundamental_divergence
else:                                watch
```

The thresholds are **heuristics**, configurable and documented — not universal market
truths. `price_strong_threshold` is the "already repriced" marker; interpreting price
relative to volatility/regime/sector is a deliberately deferred extension point (no
data to justify it yet). VVV (`pt +98.3% ≥ 50%`, improving) → `fundamental_repricing`.

## Out of scope

The full Alpha Score, advanced tokenomics, backtesting, ML, market-regime detection,
new infrastructure, on-chain data. Ranking is NOT redesigned into an opportunity
score. Valuation thresholds are NOT introduced.

## Acceptance / Exit criteria

- Cases A–G pass; VVV regression asserts VVV is **not** `fundamental_divergence`.
- Prior Sprint 05 tests updated only where behavior is intentionally corrected
  (documented), never weakened to pass.
- `divergence_score`, `divergence_gap`, `signal_strength`, `valuation_level`,
  `data_quality`, `classification` are distinct; no field collapsed.
- Migration `0005` applies and reverses; `ruff`/`mypy` clean; full suite + foundation
  gate green; Docker builds, starts, `/health` ok; scan+divergence workflow works.
- Docs (plan, report, ADR-005, `docs/data`, `docs/api`, CHANGELOG) updated; release
  `v0.5.1` tagged and published; rollback documented.

## Rollback considerations

Migration `0005` is additive (three nullable columns) with a working `downgrade()`.
Divergence signals are derived data (regenerable by re-running). `git checkout v0.5.0`
returns to the pre-refinement engine; `v0.5.0` remains the prior stable anchor.
