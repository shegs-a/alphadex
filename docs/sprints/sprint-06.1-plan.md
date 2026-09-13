# Sprint 06.1 Plan — Tokenomics & Risk Validation

## Objective

A focused validation/refinement pass over the Sprint 06 Tokenomics & Risk engines
before Sprint 07 introduces the Alpha Score. Fix only genuine semantic, scoring,
ranking, or data-quality issues found; do not redesign the engines. Preserve the
Sprint 05.1 divergence/classification contract (ADR-005) unchanged.

## Audit findings (verified against the code)

1. **`value_capture_score: 1 / label: unknown` is a genuine semantic issue.**
   `value_capture_score` blends dilution (`float_ratio`) and value capture over the
   *present* components. When only dilution is available (e.g. ETH, stablecoins:
   `float_ratio = 1.0`, no fee/revenue/holders data), the score equals `1.0` while the
   label is `unknown`. That `1.0` reads as "strong value capture" and (worse) ranked
   such assets **#1** in tokenomics — an artificial ranking advantage from missing
   data. Sprint 06 fixed the *label*; the *score* remained misleading.

2. **Risk components are absolute, clamped values** (not percentile/relative):
   - `liquidity_risk = clamp(1 − min(1, turnover/ref_turnover))`; `1.0` = zero
     turnover (no volume relative to market cap) — clamped maximum.
   - `volatility_risk = clamp(max(|Δ7d|,|Δ30d|)/ref_volatility)`; `1.0` = a swing at or
     above the reference (default 50%) — clamped (a 50% and a 200% swing both read 1.0).
   - `dilution_risk = clamp(1 − float_ratio)`; `1.0` = circulating value is 0% of FDV.
   - `size_risk = clamp(1 − log10(1+mc)/log10(1+ref_market_cap))`; `1.0` ≈ zero market
     cap.
   - `concentration_risk` is always `null` (no on-chain data).
   No correctness bug here — but the meaning of `1.0` must be documented.

3. **Genuine zeros vs unknown are already distinct** in most places: a real `0`
   numerator (e.g. revenue = 0 → `revenue_to_fees = 0.0`) is preserved and differs
   from `null` (missing). A **zero denominator** (fees = 0, revenue = 0, mc = 0) makes
   a ratio undefined and is reported as `null`/unavailable — never a false `0`.

## Scope (changes)

- **Tokenomics score semantics (fix #1):** `value_capture_score` is `None` unless a
  value-capture component (`revenue_to_fees` / `holders_to_revenue` / `real_yield`) is
  present. Dilution/float remains exposed via `float_ratio` (and contributes to the
  score only when value capture is also present). `value_capture_label` follows the
  score (`unknown` when `None`). Consequence: dilution-only assets are no longer
  scored or ranked in tokenomics — removing the artificial ranking advantage.
- **Documentation of risk normalization (fix #2):** clarify in `docs/data` and evidence
  that each risk factor is an absolute value clamped to [0,1] against a configured
  reference, and what `1.0` means per factor.
- **Regression tests** for the representative asset cases (complete/missing tokenomics,
  100% float, significant dilution, high liquidity/volatility/size risk, missing
  concentration, genuine zero values, unknown values).
- Docs (this plan, report, CHANGELOG, `docs/data`, `docs/api`), version `v0.6.1`.

## Out of scope

No Alpha Score, no schema change (`value_capture_score` is already nullable), no new
providers/on-chain data, no ML/backtesting, no volatility/regime redesign. Divergence
(ADR-005) untouched.

## Acceptance / Exit criteria

- `value_capture_score` is `null` (never a positive sentinel) when value capture is
  unmeasured; dilution-only assets are unranked in tokenomics.
- Risk `1.0` semantics documented per factor; genuine zeros preserved and distinct
  from `null`.
- Ranking semantics documented (tokenomics = value-capture measurement; risk = highest
  risk first, a warning ordering).
- Full suite + new regression tests pass; ruff/format/mypy clean; Docker builds/starts;
  `/health` ok; core workflow works. Report + CHANGELOG updated; `v0.6.1` tagged;
  rollback documented.

## Rollback considerations

Source-only change (no migration; `value_capture_score` already nullable). Tokenomics
signals are derived data — re-running the engine repopulates them under the new
semantics. `git checkout v0.6.0` returns to the prior behavior. `v0.6.0` remains the
prior stable anchor.
