# Sprint 08 Report — Valuation Engine

## Sprint objective

Build the **Valuation Engine** — relative cheapness vs the economics an asset generates
— and graduate the Alpha `valuation` component from `not_implemented` to consuming it.
The first component to slot into Alpha, and the biggest lever on the `low_confidence`
problem: for assets with valuation data, `model_completeness` rises 0.80 → 0.95.

## What shipped

- **`valuation` module** (`src/alphadex/valuation/`):
  - `multiples.py` — four pure multiples (MC / annualized fees, / annualized revenue,
    / annualized holders-revenue, / TVL), each `None` when an input is missing or a
    denominator is non-positive (never a false `0`). Distinct economic meanings, never
    collapsed (§9).
  - `score.py` — each measurable multiple → relative attractiveness `ref / (ref +
    multiple)` (lower = cheaper, 0.5 at the reference), blended with renormalized
    weights into a `valuation_score` (`None` unless a multiple was measurable), a
    label (`cheap`/`fair`/`expensive`/`unknown`), a **separate** `data_completeness`,
    and evidence surfacing both cheaper-on and richer-on sides.
  - `service.py` + `repository.py` + `config.py` — run over the candidates via the
    shared analysis base; per-asset SAVEPOINT isolation; rank by attractiveness.
- **Migration `0008`** (additive/reversible) — `valuation_runs`,
  `valuation_assessments`; the four distinct multiples + score + label +
  `data_completeness` as distinct columns. Nullable, never `0`.
- **Alpha integration** — `alpha/components.valuation` now consumes `valuation_score`
  (mirroring `token_value_capture`); `alpha/service` + `alpha/repository` load the
  latest valuation. **No change** to the Alpha formula, ranking, or the three-output
  contract (ADR-006 upheld; dated note added).
- **Read API** — `GET /valuations`, `/valuations/{asset_id}`, `/valuation-runs`. New
  `scripts/run_valuation.py`.
- Docs — README, CHANGELOG, `docs/data`, `docs/api`, roadmap reorder (08 → Valuation;
  Technical Setup deferred), and the ADR-006 note.

## Approved guardrails — how each was met

1. **Attractiveness ≠ fair value.** Field/label naming, the `evidence.basis` string
   ("NOT an intrinsic/fair-value estimate"), and docstrings all state it; a test asserts
   the basis wording. Labels are `cheap`/`fair`/`expensive` (relative), never
   "undervalued".
2. **References are heuristic baselines.** Documented as such in config, `docs/data`,
   and evidence; the reference is the point mapped to 0.5, explicitly "mid-range for
   this metric", not a market truth.
3. **Completeness separate from attractiveness.** `data_completeness` is its own field,
   never blended into `valuation_score`; a test with equal available evidence but
   differing coverage confirms the score is unchanged while completeness moves.
4. **Mixed/conflicting and single-multiple tests.** `test_mixed_conflicting_evidence...`
   (cheap on fees, expensive on TVL → blend lands between, both sides surfaced) and
   `test_single_multiple_availability...` (scored on one multiple, low completeness).
5. **Distinct economic meanings.** Four distinct denominators, columns, and evidence
   lines; `test_multiples_retain_distinct_economic_meanings` asserts they differ.
6. **No tuning to known winners.** References/weights are documented defaults; not
   fitted; tuning deferred to backtesting (Sprint 11).
7. **No redesign of Alpha/Risk/Confidence.** Only the `valuation` adapter changed;
   `test_valuation_lifts_alpha_completeness` confirms completeness reaches 0.95 with the
   formula/ranking/contract untouched, and the prior alpha invariants still pass.
8. **No Technical Setup.** It remains the sole `not_implemented` component (asserted in
   the integration test); completeness caps at 0.95.

## Verification

- **197 tests pass** (179 prior + 18 new: valuation multiples/score incl. mixed and
  single-multiple, service isolation/rank, API, and the Alpha-integration completeness
  lift). ruff + format clean; mypy clean (71 source files); foundation gate 7 passed.
- Migration `0008` applies and reverses (`test_migration` covers the new tables).
- End-to-end on Docker + PostgreSQL 16: ingest → scan → divergence → tokenomics → risk
  → **valuation** → alpha; `/valuations` populated and `/scores` shows `valuation`
  available with `model_completeness` ~0.95 for assets with data; no BUY language.

## Deviations from the plan

Sprint 08 was reordered from Technical Setup to the Valuation Engine (approved by the
user — the larger Confidence lever). No new ADR was needed; the engine consumes the
existing ADR-003/005/006 contracts, with a dated note appended to ADR-006.

## Known limitations

Valuation is coarse and absolute (market-cap multiples vs heuristic references) — no
DCF, peer/sector-relative, growth-adjusted, or historical-percentile context; a future
extension. Technical Setup remains unimplemented (completeness caps at 0.95). Coverage
still depends on fundamentals availability (Phase 1 `gecko_id` match).

## Rollback

`alembic downgrade -1` drops `valuation_runs` / `valuation_assessments`; with them
absent the Alpha `valuation` component reports unavailable again (completeness returns
to 0.80) — fully back-compatible. Valuation results are derived data, regenerable via
`scripts/run_valuation.py`. `git checkout v0.7.0` returns to the Alpha Scoring
foundation; `v0.7.0` remains the prior stable anchor.

## Release

`v0.8.0` — release commit on `claude/resume-session-devices-ibdww4`; annotated tag
pushed; GitHub Release published.
