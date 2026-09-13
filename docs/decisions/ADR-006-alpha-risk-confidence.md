# ADR-006: Alpha, Risk, and Confidence — Three Separate Outputs, and Renormalized Component Weighting

- Status: Accepted
- Date: 2026-09-13
- Sprint: 07

## Context

Sprints 02–06 produced the component signals — divergence (ADR-005), token value
capture, risk, and the market/fundamental observations. Sprint 07 assembles them into
the system's headline decision-support output. Two design hazards had to be settled
before writing the engine:

1. **Collapsing distinct concepts into one number.** A single "score" that folds
   attractiveness, risk, and how-much-we-trust-it together hides exactly the
   information a human needs, and invites blind BUY signals (AGENTS.md §10 forbids
   this).
2. **Handling components that are not built yet.** The AGENTS.md §10 default Alpha
   weight vector includes **Valuation** (15) and **Technical Setup** (5) — 20% of the
   intended weight — which have no engine yet. Zero-filling them would understate every
   asset and violate the missing-data contract (ADR-003); blocking Alpha until they
   exist would delay the payoff by two-plus sprints.

## Decision

### 1. Three separate outputs, never one number (§10)

- **Alpha Score** — a configurable weighted blend of the *attractiveness* components
  only. It determines ranking.
- **Risk Score** — taken as-is from the Risk engine (Sprint 06) and surfaced
  **alongside** Alpha. It is **never** folded into the Alpha formula.
- **Confidence** — how much to trust the Alpha Score, from data completeness and
  upstream data quality. Also **never** folded into Alpha.

Risk and Confidence influence the **decision status** (down-classification) and
Confidence breaks ranking ties, but neither changes the Alpha number itself. A high
Alpha with elevated Risk or low Confidence is down-classified (`risk_elevated` /
`low_confidence`), never surfaced as a top opportunity, and never expressed as BUY.

### 2. Absent components: renormalize, and reflect the absence in Confidence

The Alpha Score is computed over the components that are **implemented and available
for the asset**, with weights **renormalized** over what is present:

```
alpha = Σ(wᵢ · vᵢ) / Σ(wᵢ)     over available components i
```

This is a weighted **average** of the available contributions (each in [0, 1]), so the
result is bounded by their minimum and maximum. **A missing component can never push
Alpha above what the present evidence supports** — the no-inflation invariant. The full
7-component target vector lives in config now, so the intended model is explicit and
stable, and Valuation/Technical slot in automatically (and Confidence rises) when they
land. Absent components are **never zero-filled** (ADR-003).

Their absence is carried by **`model_completeness`** = (sum of available component
weights) ÷ (sum of all target weights). With Valuation and Technical unimplemented,
completeness is capped at 0.80, which honestly constrains Confidence until those
engines exist.

### 3. Ranking is completeness-aware so missing data buys no advantage

Ranking is by Alpha Score descending, with **`model_completeness` breaking ties toward
the more-complete asset**. So when two assets have identical available evidence and
therefore an identical (renormalized) Alpha, the one that is missing components does
**not** out-rank the more-complete one — renormalization is a normalization, not a
bonus. A shorter component set can only out-rank a complete one when the complete
asset's *additional real evidence is genuinely weak*, which is true signal (and the
shorter asset's lower Confidence flags the uncertainty).

### 4. Divergence feeds Alpha via its classification, not the raw gap

The divergence Alpha component is driven by the ADR-005 **classification**:
`potential_mispricing` and `fundamental_divergence` contribute positively;
`fundamental_repricing` and `momentum` contribute little (the market has already moved);
`thesis_weakening` contributes a genuine zero. This prevents the VVV trap (repricing
scored as opportunity) and avoids double-counting price momentum, which lives only in
the small, separate `market_strength` component.

### 5. Decision status uses the allowed vocabulary only (§10)

`high_interest`, `potential_opportunity`, `watch`, `risk_elevated`, `low_confidence`,
`thesis_weakening`, `insufficient_data`. Never BUY/GUARANTEED. Down-classification
order: insufficient data → low confidence → elevated/high risk → weakening thesis →
then the Alpha band.

## Alternatives considered

- **A single blended opportunity score.** Rejected (§10): hides risk and confidence,
  invites blind BUY.
- **Zero-fill unimplemented components.** Rejected: understates every asset and treats
  missing as a real low value (violates ADR-003).
- **Block the Alpha Score until Valuation + Technical exist.** Rejected: delays the
  system's payoff for a partial-information problem the missing-data discipline already
  solves cleanly.
- **Fold Risk (e.g. `alpha · (1 − risk)`) or Confidence into Alpha.** Rejected:
  re-collapses the three outputs; a human can no longer see *why* something ranks where
  it does.
- **Rank by Alpha alone, ignoring completeness.** Rejected: lets an asset with missing
  components tie or leapfrog a fully-evidenced one purely through renormalization.

## Rationale

Keeping Alpha, Risk, and Confidence separate — and treating unimplemented components as
just another kind of missing data (renormalize + reflect in Confidence, never
zero-fill) — is the same discipline as ADR-003 and ADR-005 applied to the final
combination step. It ships a working, honest Alpha Score now, degrades gracefully, and
grows into the full model without a rewrite.

## Consequences

- **Positive:** three legible outputs; a working ranked opportunity list today;
  Confidence honestly capped (~0.8) until Valuation/Technical land, then improving with
  no engine rewrite; missing data never inflates a score or a rank; no blind BUY.
- **Negative:** more moving parts (weights, references, thresholds, bands) to maintain
  and test; the default weights are documented AGENTS.md defaults, deliberately **not**
  fitted to any known outcomes (no hindsight bias, §10) — principled tuning is a
  backtesting concern (Sprint 11).
