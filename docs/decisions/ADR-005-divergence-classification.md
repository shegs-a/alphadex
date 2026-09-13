# ADR-005: Divergence — Measurement vs. Interpretation, and Semantic Classification

- Status: Accepted
- Date: 2026-09-13
- Sprint: 05.1

## Context

The Sprint 05 Divergence Engine computed a signed economic-price gap
(`fundamentals_trend − price_trend`) and labeled anything with a positive gap above
a threshold as `fundamental_divergence`. This conflated a **measurement** (there is a
gap between fundamental growth and price growth) with an **interpretation** (this is
an undiscovered mispricing worth acting on).

The failure was concrete: **VVV** had `fundamentals_trend +155.8%` and
`price_trend +98.3%`. Because `155.8% > 98.3%`, it was labeled
`fundamental_divergence` and ranked #1 — even though the price had *already* risen
+98%. That is not the thesis. AlphaDex's thesis (§1) is that fundamentals are
improving faster than the market **is recognizing** — which requires that price has
*not* already repriced.

## Decision

Separate **divergence measurement** from **opportunity interpretation**, and express
interpretation as a set of semantic classifications keyed off the **price regime**,
not just the sign of the gap.

1. **Measurement fields are distinct and preserved** (never collapsed into one):
   `fundamentals_trend`, `price_trend`, `divergence_gap` (raw `ft − pt`),
   `divergence_score` (blended, clamped, signed), `signal_strength` (magnitude),
   `valuation_level`, `valuation_trend`, and `data_quality`.

2. **Classification** (the interpretation) is one of:
   - `potential_mispricing` — fundamentals improving materially while price is
     declining or stagnant.
   - `fundamental_divergence` — fundamentals improving materially faster than price,
     with price **not** already strongly repriced.
   - `fundamental_repricing` — fundamentals improving strongly **and** price also
     rising strongly (the market may already be recognizing it).
   - `momentum` — price rising strongly without material fundamental support.
   - `thesis_weakening` — fundamentals deteriorating materially.
   - `watch` — none of the above.
   - `insufficient_data` — required inputs missing (score is `NULL`, never `0`).

3. **Price behavior influences classification** via configurable, documented
   heuristics — a materiality floor (`min_fundamentals_improvement`), a
   "stagnant/declining" ceiling (`price_stagnant_ceiling`), and an "already repriced"
   marker (`price_strong_threshold`). These are **heuristics, not universal market
   truths**; interpreting price relative to volatility/regime/sector/history is a
   deliberate future extension point (no data to justify it yet).

4. **Data quality is separate from signal strength** and does **not** silently
   reduce the score. A strong signal on thin data is reported as strong signal +
   low data quality, not as an artificially weak score.

5. **Ranking remains a preliminary divergence-*measurement* ranking** (by
   `divergence_score`), explicitly documented as "largest measured economic-price
   gap", not "best opportunity". Folding data quality, valuation, value capture, and
   risk into a single opportunity ranking is the **Alpha Score's** job (Sprint 07).

## Alternatives considered

- **Keep gap-sign-only classification.** Rejected: mislabels repricing/momentum as
  divergence (the VVV failure); misrepresents the core thesis.
- **A single hard-coded price cutoff (e.g. `price > 50% → repricing`) with no
  configuration or rationale.** Rejected as too crude and undocumented; instead the
  cutoff is a configurable, documented heuristic with a clean extension point.
- **Multiply `divergence_score` by `data_quality`.** Rejected: collapses two
  distinct concepts and hides low confidence inside a plausible-looking score.

## Rationale

The distinction between "there is an economic-price gap" and "this is an
opportunity" is foundational to AlphaDex. Encoding it explicitly — measurement fields
plus a price-regime-aware classification — keeps signals honest, makes explanations
truthful, and prevents momentum from masquerading as undiscovered value.

## Consequences

- **Positive:** VVV is now `fundamental_repricing`, not `fundamental_divergence`;
  genuine mispricings (fundamentals up, price lagging) are named as such;
  measurement and confidence are legible and separable; downstream engines
  (Alpha Score, Sprint 07) inherit clean inputs.
- **Negative:** more classifications and heuristics to maintain and test; the
  heuristic thresholds will need tuning and, eventually, regime/volatility awareness.
  Accepted; the thresholds are configurable and covered by the case-matrix tests.
