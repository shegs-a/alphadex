# Sprint 05.1 Report — Divergence Engine Diagnostic & Refinement

## Sprint objective

Refine the Sprint 05 Divergence Engine so it distinguishes genuine economic-price
**divergence** from **fundamental repricing / momentum**. A positive mathematical gap
is a *measurement*, not an *opportunity interpretation*. Keep the change small,
explainable, tested, and reversible.

## Final report — required answers

**1. What caused VVV to be incorrectly classified.**
The classifier used a single rule: `divergence_score >= threshold AND
fundamentals_improving → fundamental_divergence`. It never considered whether price
had *already* risen. VVV (`fundamentals_trend +155.8%`, `price_trend +98.3%`,
`gap 0.575`) satisfied it purely because `155.8% > 98.3%`, so it was labeled
`fundamental_divergence` and ranked #1 — despite price already being up +98%.

**2. What changed in the classification logic.**
Introduced a price-regime-aware classifier ([engine.py](../../src/alphadex/divergence/engine.py)
`_classify`) with seven semantic classes: `potential_mispricing`,
`fundamental_divergence`, `fundamental_repricing`, `momentum`, `thesis_weakening`,
`watch`, `insufficient_data`. Measurement and interpretation are now separate
(ADR-005): the signed gap/score/`signal_strength` are the *measurement*; the
`classification` is the *interpretation*.

**3. How the engine now distinguishes divergence from repricing.**
By fundamentals materiality **and price regime** (configurable heuristics):

```
declining (ft ≤ -0.05)                         → thesis_weakening
price_strong (pt ≥ 0.50): improving → fundamental_repricing ; else → momentum
improving and gap ≥ threshold:
    price ≤ 0.05 (flat/down) → potential_mispricing
    else                     → fundamental_divergence
otherwise                                       → watch
```

VVV (`pt +98.3% ≥ 0.50`, improving) → `fundamental_repricing`. Verified live.

**4. Whether and how price behavior influences classification.**
Yes. Two configurable, documented heuristics: `price_stagnant_ceiling` (default 0.05,
"declining/stagnant") and `price_strong_threshold` (default 0.50, "already
repriced"). These are explicitly heuristics, not universal truths; interpreting price
relative to volatility/regime/sector is a documented future extension point.

**5. Whether data quality influences ranking yet.**
No — deliberately. `data_quality` is recorded and kept **separate** from
`signal_strength` (it is not multiplied into the score). Ranking is a preliminary
divergence-*measurement* ranking (by `divergence_score`), now documented as such in
the API. Quality-weighting is the Alpha Score / Confidence's job (Sprint 07).

**6. Whether valuation influences ranking yet.**
No. The valuation multiple (`valuation_level`) is informational evidence; only its
cross-time change (`valuation_trend`) feeds the score, and only when history exists
(currently null). No valuation thresholds were introduced.

**7. Why those decisions were made.**
To keep the thesis honest: a positive gap is not automatically an opportunity, and a
strong signal on thin data must not masquerade as either a weak signal or a
high-confidence one. Keeping measurement, interpretation, and confidence as distinct
concepts (ADR-005) is foundational and keeps later engines' inputs clean.

**8. What remains intentionally deferred to Sprint 06/07.**
The Alpha Score / Risk Score / Confidence trio (07); tokenomics value capture and the
Risk engine (06); folding data-quality/valuation/risk into an opportunity ranking
(07); volatility/regime-aware price interpretation (future); on-chain data.

**9. Test results.**
`uv run pytest`: **121 passed**. ruff clean; format clean; mypy success (41 source
files); foundation gate 7 passed. Docker build + startup + `/health` (0.5.1) verified;
migration `0005` applied on PostgreSQL 16; live re-run reclassified VVV to
`fundamental_repricing`.

**10. Release version.** `v0.5.1`.

**11. Git commit/tag.** Release commit on `claude/resume-session-devices-ibdww4`;
annotated tag `v0.5.1` at the release head (pushed; GitHub Release published).

**12. Rollback procedure.** `alembic downgrade -1` drops the three added columns
(`divergence_gap`, `signal_strength`, `valuation_level`); signals are derived data,
regenerable by re-running the engine. `git checkout v0.5.0` returns to the
pre-refinement engine. `v0.5.0` remains the prior stable anchor.

## Completed tasks

- Diagnosed and documented current behavior against the code (see plan) before
  changing anything.
- Semantic classifications + price-regime classifier; measurement/interpretation
  separation; `signal_strength`, `divergence_gap`, `valuation_level` fields.
- Evidence language corrected (7d/30d run-rate phrasing; `evidence_strength`).
- Config: removed `divergence_weakening_threshold`; added
  `divergence_price_stagnant_ceiling` and `divergence_price_strong_threshold`.
- Migration `0005` (additive/reversible). ADR-005. Docs (plan, this report,
  `docs/data`, `docs/api`, README, CHANGELOG, `.env.example`).
- Tests: case matrix A–G incl. VVV regression; updated Sprint 05 tests where behavior
  was intentionally corrected (documented below).

## Intentionally changed test expectations (regression protection)

Per spec §12, these Sprint 05 expectations were corrected, not weakened:
- `test_divergence_service::test_run_persists_ranked_signals`: a fees-accelerating /
  price-falling asset is now `potential_mispricing` (was `fundamental_divergence`).
- `test_api_divergences::test_list_divergences_with_evidence`: same asset now
  `potential_mispricing`; asserts new measurement fields + `evidence_strength`.
- `test_divergence_config`: `weakening_threshold` removed; price-ceiling ordering
  validation added.
- Old "flat-price cross-time → fundamental_divergence" expectation replaced by
  "→ potential_mispricing" (price flat is the mispricing regime).

## Database changes

Migration `0005` adds nullable `divergence_gap` (Numeric 18,8), `signal_strength`
(Numeric 9,6), and `valuation_level` (Numeric 38,18) to `divergence_signals`. No
other schema change.

## Known limitations / deferred

Price interpretation uses fixed heuristic thresholds (no volatility/regime awareness
yet). Track B still depends on accumulated history (unchanged from Sprint 05). Ranking
is measurement-only by design until the Alpha Score (Sprint 07).

## Release / rollback

- Version **v0.5.1**; tag `v0.5.1`; GitHub Release published.
- Rollback: `alembic downgrade -1` (drops the 3 columns) or `git checkout v0.5.0`.

## Definition of Done — met

AlphaDex now detects an economic-price gap **without** automatically calling every
positive gap an opportunity: it states "fundamentals are improving faster than price"
(measurement) and separately determines whether that is genuine divergence,
repricing, momentum, or insufficient evidence (interpretation). Sprint 06 is not
started until this report and the `v0.5.1` release are complete.
