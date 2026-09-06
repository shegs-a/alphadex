# Architecture Overview

Status: **Sprint 00 (foundation).** This describes the intended architecture. Code
lands from Sprint 01 onward; where a component does not yet exist it is marked
_(planned)_.

---

## 1. Shape: modular monolith

AlphaDex Scout is a single deployable application composed of clearly bounded
internal modules. It is **not** a set of microservices. Scheduled ingestion runs
in-process. The whole system runs identically on a laptop and a small cloud VM via
Docker Compose. Rationale: `docs/decisions/ADR-001-modular-monolith.md`.

```
                        ┌─────────────────────────┐
                        │        API layer         │  FastAPI (planned)
                        │  /health /assets /...     │
                        └────────────┬─────────────┘
                                     │
        ┌────────────────────────────┼────────────────────────────┐
        ▼                            ▼                            ▼
 ┌───────────────┐          ┌────────────────┐          ┌──────────────────┐
 │   Ingestion   │          │  Normalization │          │   Alpha Engine   │
 │  (providers)  │  raw →    │  + Validation  │  clean →  │ divergence /     │
 │ market/fund./ │─────────▶│  internal model│─────────▶│ valuation / risk │
 │ tokenomics    │          │                │          │ / scoring        │
 └───────┬───────┘          └───────┬────────┘          └────────┬─────────┘
         │                          │                            │
         │                          ▼                            │
         │                 ┌─────────────────┐                  │
         └────────────────▶│   PostgreSQL    │◀─────────────────┘
                           │ (observations,  │
                           │  entities,      │
                           │  scores)        │
                           └─────────────────┘

 Scheduler (APScheduler, in-process, planned) drives tiered ingestion + scans.
```

---

## 2. Modules and responsibilities

Internal boundaries — each is a package/subpackage under `src/alphadex/`, not a
separate deployable service.

| Module | Responsibility |
|---|---|
| **Market Data** | Price, market cap, FDV, supply, volume, historical price, volatility, relative performance. |
| **Fundamental Data** | Fees, revenue, holders revenue, earnings, TVL, users/activity, transactions, growth over 7/30/90d. |
| **Tokenomics** | Supply, FDV, inflation, unlocks, dilution, allocation, concentration, emissions, staking, value capture. |
| **Normalization** | Validate raw provider data; convert to the internal data model with explicit missing-data markers and provenance. |
| **Opportunity Scanner** | Tiered screening of the asset universe (cheap → deep). |
| **Divergence Engine** | Detect economic-vs-price divergence across multiple independent models. |
| **Valuation Engine** | Multiples and yields, adjusted for growth, value capture, dilution, sector, liquidity. |
| **Risk Engine** | Independent risk model (liquidity, volatility, unlocks, dilution, concentration, data quality, …). |
| **Scoring Engine** | Explainable composite Alpha Score from configurable component weights. |
| **Technical Analysis** | Timing layer (trend, S/R, momentum, structure) — never the primary discovery engine. |
| **Reporting** | Ranked candidates with human-readable explanations. |
| **Notifications** | Delivery (e.g. Telegram) — later sprint. |
| **API** | FastAPI resources exposing the above. |
| **Dashboard** | UI — deferred until a real requirement (Sprint 10). |

---

## 3. Data flow: raw → normalized

External data is unreliable, so raw and normalized data are strictly separated:

```
Provider Data → Validation → Normalization → Internal Data Model
```

- **Provider abstraction:** business logic depends on interfaces
  (`MarketDataProvider`, `FundamentalDataProvider`, `TokenomicsProvider`,
  `HistoricalDataProvider`), so a provider can be swapped without touching the
  scoring engine.
- **Missing data is explicit** (`UNKNOWN` / `NOT_AVAILABLE` / `NOT_APPLICABLE`),
  never `0` (ADR-003).
- **Metric distinctions preserved:** Fees ≠ Revenue ≠ Holders Revenue ≠ Price
  Appreciation.
- **Provenance preserved:** provider, timestamp, metric, asset, period, source
  status, freshness.

---

## 4. Persistence: append-only observations

Core analytical data is stored as historical **observations**
(`asset, metric, value, period, observed_at, source`), not just current values, so
the system is backtestable from day one (ADR-004). Core entities use structured
relational schemas managed by Alembic migrations; JSONB is reserved for genuinely
flexible provider-specific metadata.

---

## 5. Pipeline and tiered processing

To control cost and API usage, processing is tiered:

```
Broad universe (~10k)
   → cheap screening
      → candidates (200–500)
         → deeper analysis
            → alpha candidates (30–100)
               → richest analysis
                  → high-conviction setups (5–20)
                     → highest-frequency monitoring
```

Expensive data is never fetched for assets that fail the initial screen.

---

## 6. Outputs

Three **separate** outputs — Alpha Score, Risk Score, Confidence — plus an
explanation for every signal (why interesting, why now, what changed, supporting
and contradicting evidence, what could invalidate it, the major risk). No blind
BUY signals; language stays evidential ("potential opportunity", "watch",
"fundamental divergence", "risk elevated", "thesis weakening").

---

## 7. Local ↔ cloud parity

One `docker-compose.yml` (Sprint 01) brings up the application + PostgreSQL with
health checks and a persistent DB volume, configured entirely via environment
variables. The same composition runs on a developer machine and on a single cloud
VM. Kubernetes/ECS/EKS, message buses, and service meshes are explicitly out of
scope until real scale justifies them.

---

## 8. Cross-cutting concerns

- **Config:** env-driven via `pydantic-settings`; documented in `.env.example`;
  no hard-coded secrets; scoring weights configurable.
- **Logging:** structured (`structlog`) — what/when/asset/provider/outcome/why;
  never secrets.
- **Error handling:** one asset's provider failure is recorded and skipped; the
  pipeline continues where safe; failures are observable, never swallowed.
- **Health:** `/health` distinguishes application / database / provider / pipeline
  health; the app is not reported healthy when a critical dependency is down.
