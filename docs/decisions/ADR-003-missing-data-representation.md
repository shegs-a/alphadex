# ADR-003: Explicit Missing-Data Representation

- Status: Accepted
- Date: 2026-09-06
- Sprint: 00

## Context

External crypto data is unreliable: metrics are frequently missing, stale, not yet
reported, or simply not applicable to a given asset category (e.g. "fees" for a
pure L1, "unlock schedule" for a fully-circulating token). Silently substituting
`0` for missing data corrupts every downstream calculation — divergence, valuation
multiples, risk, and the Alpha Score — and produces confident-looking but false
signals. Data integrity is a top-two priority for this system.

## Decision

Missing or non-applicable data is represented **explicitly**, never as `0` or an
empty default. The system distinguishes at least three states:

- **`UNKNOWN`** — the value exists in reality but we could not obtain it (provider
  error, not fetched yet).
- **`NOT_AVAILABLE`** — the provider genuinely does not supply this metric for this
  asset, or it has not been reported for the period.
- **`NOT_APPLICABLE`** — the metric does not apply to this asset's category.

Rules:

1. A metric value carries its state; absence is a first-class value, not `null`
   coerced to `0`.
2. Calculations must handle these states deliberately — propagate as
   missing/`UNKNOWN`, exclude from aggregates, or (rarely, and documented) apply a
   defined fallback. They must never treat missing as `0`.
3. Data completeness feeds **Confidence**: more missing inputs lower confidence.
   Missing data never silently inflates or deflates a score.
4. The concrete storage encoding (e.g. nullable columns + a status enum, or a small
   value-object) is fixed when the data model is implemented in Sprint 01/02;
   the semantic contract above is binding regardless of encoding.

## Alternatives considered

- **Use `0`/empty defaults.** Rejected: silently corrupts divergence, valuation,
  and risk; the exact failure this system must avoid.
- **Use only SQL `NULL`.** Insufficient alone: `NULL` cannot distinguish "unknown"
  from "not applicable" from "not reported", which matters for both correctness and
  confidence. A status/enum alongside the value is required.

## Rationale

Preserving the distinction between the three missing states protects correctness
and data integrity, keeps confidence honest, and makes explanations truthful ("we
could not obtain revenue" ≠ "revenue is zero"). It also keeps backtests valid by
never inventing data that was not available at the time.

## Consequences

- **Positive:** trustworthy scores, honest confidence, truthful explanations,
  valid backtests.
- **Negative:** every calculation and query must consciously handle the missing
  states — more code and more tests. This cost is accepted; data-quality tests will
  assert missing data is never coerced to `0`.
