# Sprint 06.1 Report — Tokenomics & Risk Validation

## Sprint objective

A focused validation/refinement pass over the Sprint 06 Tokenomics & Risk engines
before Sprint 07's Alpha Score. Fix genuine semantic/scoring/ranking/data-quality
issues only; no redesign; preserve the Sprint 05.1 divergence contract (ADR-005).

## Final report — required answers

**1. Was `value_capture_score: 1 / unknown` a semantic issue?**
**Yes.** `value_capture_score` blended dilution (`float_ratio`) and value capture over
the *present* components. When only dilution was available (ETH, stablecoins:
`float_ratio = 1.0`, no fee/revenue/holders data), the score was `1.0` while the label
was `unknown` — and those assets ranked **#1** in tokenomics. A `1.0` "value capture"
on an asset whose value capture is entirely unmeasured is a real conflation of
`UNKNOWN` with a strong `KNOWN` score, and it created an artificial ranking advantage.

**2. How are unknown values now represented?**
`value_capture_score` is **`null`** unless a value-capture component
(`revenue_to_fees` / `holders_to_revenue` / `real_yield`) is actually present; the
label follows the score (`unknown` when `null`). Dilution is no longer able to stand
in for value capture — it remains exposed separately as `float_ratio` (its own
measurement). Consequently dilution-only assets are unscored and **unranked** in
tokenomics. Genuine zeros are preserved and distinct from `null`: e.g. `revenue = 0`
→ `revenue_to_fees = 0.0` (a measured value); a zero denominator (fees/revenue/mc = 0)
makes the ratio undefined and is reported as `null`, never a false `0`.

**3. What does `risk_score = 1` mean for each risk component?**
Each factor is an **absolute value clamped to [0,1]** against a configured reference
(not a percentile/relative rank):
- `liquidity_risk = 1.0` → zero 24h turnover (no volume relative to market cap).
- `volatility_risk = 1.0` → a price swing at or above `ref_volatility` (default 50%);
  larger swings also clamp to 1.0.
- `dilution_risk = 1.0` → circulating value is 0% of fully diluted (maximum overhang).
- `size_risk = 1.0` → market cap near zero.
- `concentration_risk` → always `null` (no on-chain data; a surfaced gap).
A blended `risk_score` near 1.0 means the available factors are jointly at/near their
clamped maxima. No correctness bug was found; the meaning is now documented
(`docs/data`).

**4. Did ranking behavior change?**
**Tokenomics: yes** — dilution-only assets (e.g. ETH) are no longer scored, so they
drop out of the tokenomics ranking instead of topping it; ranking now reflects genuine
value-capture measurement only. **Risk: no change** — still ordered by `risk_score`
highest-first (a warning ordering, not an opportunity ranking), documented as such.
Missing data no longer creates an artificial ranking advantage in tokenomics.

**5. What remains deferred to Sprint 07?**
The Alpha Score / Confidence trio (combining divergence + value capture + market
signals, and giving data quality a role in opportunity ranking); on-chain holder
concentration and precise unlock schedules; volatility/regime-aware models; the
migration of Scanner/Divergence services onto the shared analytical base.

**6. Test results.**
`uv run pytest`: **148 passed** (145 prior + net new tokenomics regression tests).
ruff + format clean; mypy success (57 files); foundation gate 7 passed. Docker build +
startup + `/health` (0.6.1) verified; a live re-run shows ETH/100%-float assets as
`value_capture_score: null` / `unknown` and unranked; risk unchanged.

**7. Release version.** `v0.6.1`.

**8. Git commit/tag.** Release commit on `claude/resume-session-devices-ibdww4`;
annotated tag `v0.6.1` (pushed; GitHub Release published).

**9. Rollback procedure.** Source-only change (no migration; `value_capture_score`
already nullable). Tokenomics signals are derived data — re-running the engine
repopulates them under the new semantics. `git checkout v0.6.0` returns to the prior
behavior. `v0.6.0` remains the prior stable anchor.

## Audit summary (Task 1 — score semantics)

| Output | Kind | Missing | Genuine 0 |
|---|---|---|---|
| `value_capture_score` | normalized score (value capture; blends dilution when VC present) | `null` | possible (0 VC) |
| `float_ratio` | measured ratio [0,1] | `null` | possible |
| `revenue_to_fees` / `holders_to_revenue` | measured ratio [0,1] | `null` (incl. zero denominator) | `0.0` preserved |
| `real_yield` | measured proxy (≥0) | `null` | `0.0` preserved |
| `data_completeness` / `data_quality` | coverage fraction [0,1] | n/a | `0.0` = nothing available |
| risk factors | normalized, clamped [0,1] (absolute) | `null` (concentration always) | `0.0` preserved |
| `risk_score` | blended [0,1] | `null` | possible |

`UNKNOWN` (`null`), `NOT_APPLICABLE`/undefined (zero denominator → `null`), genuine
`ZERO` (`0.0`), and `KNOWN` (a real value) are kept distinct.

## Changes

- `src/alphadex/tokenomics/score.py`: `value_capture_score` is `None` unless a
  value-capture component is present; label follows the score; docstring updated.
- Tests: tokenomics regression cases (100% float, significant dilution, dilution-only
  → null, genuine zero vs unknown, value-capture-present → real score).
- Docs: this report + plan, CHANGELOG (`0.6.1`), `docs/data` (risk `1.0` semantics,
  tokenomics score/zero/null semantics), `docs/api` (score-null + ranking semantics).

## Deviations from the plan

None. No risk-model change was required (audit found no correctness bug — only
documentation was needed). No schema change.

## Rollback procedure

`git checkout v0.6.0`; re-run `scripts/run_tokenomics.py` if repopulating. No migration
to reverse.
