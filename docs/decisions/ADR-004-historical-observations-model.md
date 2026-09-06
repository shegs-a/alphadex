# ADR-004: Historical Observations Data Model

- Status: Accepted
- Date: 2026-09-06
- Sprint: 00

## Context

Future AlphaDex versions must be able to ask *"Would this signal have identified the
opportunity before the market repriced it?"* — i.e. the system must be
**backtestable**. Divergence detection also inherently compares change over time
(revenue ↑ while price ↓ over 30 days). An architecture that stores only
`current_value` for each metric destroys the history needed for both, and cannot be
reconstructed after the fact.

## Decision

Store metric data as **append-only historical observations**, not mutable current
values. The logical shape of an observation is:

```
asset        — which asset (internal id)
metric       — which metric (e.g. revenue, fees, market_cap), with its unit
value        — the observed value, or an explicit missing-data state (ADR-003)
period       — the period the value covers (e.g. 2026-08, 7d, point-in-time)
observed_at  — when we recorded it (our timestamp)
source       — provenance: provider, provider timestamp, source status, freshness
```

Rules:

1. Observations are **append-only**; corrections are new rows, not overwrites, so
   history is preserved and auditable.
2. "Current value" is a **query** over observations (latest for asset+metric+period),
   not a stored, overwritten field.
3. Every observation carries provenance sufficient to answer "this value came from
   provider X, retrieved at time Y".
4. Backtests and any point-in-time analysis must read observations **as of** a
   given time — never use data recorded after the decision point (no hindsight
   bias / no lookahead).
5. Core entities (assets, metrics) use structured relational schemas via Alembic
   migrations; JSONB is reserved for flexible provider-specific metadata, not for
   core analytical values.

## Alternatives considered

- **Store only current values** (one row per asset+metric, overwritten). Rejected:
  no history, no backtesting, no divergence-over-time, unauditable.
- **Log everything as raw JSON blobs.** Rejected: core analytical data needs
  structured, queryable, indexed schemas; the spec warns against JSON-blob-
  everything. JSONB stays for genuinely flexible metadata only.
- **Separate time-series database.** Rejected for now: adds a second datastore;
  PostgreSQL handles this volume well with appropriate indexes. Revisit only if
  scale demands it (would require a new ADR).

## Consequences

- **Positive:** backtestability from day one, native divergence-over-time, full
  auditability and provenance, point-in-time correctness.
- **Negative:** more rows and larger storage than a current-value model; requires
  indexes and, later, retention/partitioning strategy. Accepted; addressed with
  indexing now and partitioning later if needed.
- The concrete schema (tables, indexes, keys) is implemented in Sprint 01/02 under
  this contract.
