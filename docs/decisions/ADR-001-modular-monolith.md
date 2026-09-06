# ADR-001: Modular Monolith

- Status: Accepted
- Date: 2026-09-06
- Sprint: 00

## Context

AlphaDex Scout must ingest a broad crypto universe, normalize unreliable external
data, and run a multi-stage analytical pipeline (divergence → valuation → risk →
scoring). It must run locally on a laptop and on a small cloud VM with minimal
environmental differences, be maintainable by a small team, and be workable by AI
coding agents. The product spec explicitly warns against premature adoption of
Kubernetes, ECS/EKS, Kafka, service meshes, and distributed microservices.

## Decision

Build AlphaDex Scout as a **modular monolith**: one deployable application with
strong internal module boundaries (Market Data, Fundamental Data, Tokenomics,
Normalization, Opportunity Scanner, Divergence, Valuation, Risk, Scoring, Technical
Analysis, Reporting, Notifications, API). Scheduled ingestion runs **in-process**
initially (APScheduler). A single Docker Compose composition brings up the
application plus PostgreSQL.

Module boundaries are enforced by package structure and dependency direction
(business logic depends on provider interfaces, not concrete APIs), so a module can
later be extracted into a separate service if — and only if — a concrete need
arises.

## Alternatives considered

1. **Microservices from the start.** Rejected: massive operational overhead
   (networking, deployment, observability, data consistency) with no scale
   requirement yet; contradicts the spec; slows a small team.
2. **Serverless functions + managed queues.** Rejected: harder local/cloud parity,
   cold-start and cost unpredictability, poor fit for a stateful analytical
   pipeline at this stage.
3. **Separate worker service now (API + worker split).** Deferred: reasonable
   later, but not yet justified. A single process with an in-process scheduler is
   simpler to run and test. Revisit when ingestion volume or reliability needs
   demand isolation.

## Rationale

- Local ↔ cloud parity is trivial with one Compose file.
- Strong module boundaries capture most of the maintainability benefit of services
  without the distributed-systems cost.
- Easiest to test end-to-end and cheapest for AI agents to reason about.
- Reversible: clean boundaries make a future service split a bounded refactor, not
  a rewrite.

## Consequences

- **Positive:** simple deployment, fast iteration, straightforward transactions and
  testing, low cost.
- **Negative:** all modules scale together; a runaway ingestion job shares
  resources with the API. Mitigated by tiered processing and, later, an optional
  worker split.
- **Guardrail:** any move toward microservices/orchestration requires a new ADR
  documenting the concrete driver (scale, independent deployment, reliability,
  processing, team ownership, or infra constraint).
