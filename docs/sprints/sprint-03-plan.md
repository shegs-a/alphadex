# Sprint 03 Plan — Fundamental Intelligence

## Objective

Add the second data domain — **protocol fundamentals** — behind a
`FundamentalDataProvider` interface, with a first concrete provider (DefiLlama).
Fetch fees, revenue, and TVL for protocols, **match them to assets already in the
universe** (by the provider-neutral CoinGecko id), validate and normalize them into
append-only `metric_observations` under a `fundamental.*` namespace with explicit
missing-data and provenance, and expose a read-only `/fundamentals` endpoint.
Result: `scripts/ingest_fundamentals.py` enriches known assets with protocol
economics, keeping **Fees ≠ Revenue ≠ Holders Revenue ≠ Price** strictly distinct.

## Phasing decision (asset ↔ protocol matching)

**Phase 1 (this sprint):** match protocols to assets **strictly by `gecko_id`**.
A DefiLlama protocol that is not in the CoinGecko universe (or has no `gecko_id`)
is **skipped and counted** — never force-created. This keeps the data model clean
and gets us to a solid, trustworthy application first: every asset that carries
fundamentals also has market data, so the two domains always align.

**Deferred to a later version (v2):** creating assets for unmatched protocols to
broaden fundamentals coverage, and deciding how to manage that alignment (protocols
with no token, multiple tokens, tokens not on CoinGecko). That is an explicit,
separate decision — not this sprint.

## Problem being solved

Sprint 02 gave the system market state (price, market cap, volume). But the whole
thesis is **divergence between improving fundamentals and lagging price** — which
is impossible without fundamentals. Sprint 03 brings in the "protocol is becoming
economically stronger" signal (AGENTS.md §1, distinction #1), deliberately kept
separate from "the token benefits" and "the price moved". It reuses the Sprint 02
provider/normalization/ingestion pattern for a second domain, proving that pattern
generalizes before the Scanner (Sprint 04) and Divergence Engine (Sprint 05) consume
both domains.

## Scope

- **Provider interface + first concrete provider**
  - `src/alphadex/providers/base.py` (extend) — `FundamentalDataProvider`
    interface + a `RawFundamentalSnapshot` DTO (protocol identity: slug, name,
    `gecko_id`, symbol, optional category; optional numeric fields for TVL and
    fees/revenue over 24h/7d/30d). Reuse the existing `ProviderError` hierarchy.
  - `src/alphadex/providers/defillama.py` — `DefiLlamaProvider` (sync httpx,
    injectable client for offline tests). Internally joins DefiLlama's fees/revenue
    overview with protocol TVL by slug; only DefiLlama-shaped keys live here.
  - Extend `providers/factory.py` with `build_fundamental_data_provider(settings)`.
- **Normalization + ingestion** (module boundaries: Fundamental Data ·
  Normalization)
  - `src/alphadex/fundamentals/normalize.py` — map validated raw fields to
    `fundamental.*` observations with correct metric name, unit, and period;
    **absent values become an explicit `ValueStatus` (`NOT_AVAILABLE`), never `0`**.
  - `src/alphadex/fundamentals/service.py` — fetch protocols, **resolve each to an
    existing internal `Asset` by matching `gecko_id` to that asset's `coingecko`
    `asset_source_ids.external_id`**, attach a `defillama` source id to the same
    asset, normalize, and append observations. Per-asset SAVEPOINT isolation and an
    `ingestion_runs` record (reuse Sprint 02 infrastructure). Protocols with no
    matching in-universe asset are recorded as skipped (tiered processing, §9 — do
    not create fundamentals for assets that failed the market screen).
  - `src/alphadex/fundamentals/repository.py` — latest fundamental observation per
    (asset, metric, period).
- **Read API** — `GET /fundamentals` (read-only), mirroring `/market-data`:
  latest `fundamental.*` observation per asset/metric/period with `value_status`,
  provenance, and freshness. Kept a separate endpoint to preserve the domain
  distinction in the API surface.
- **Ingestion entrypoint** — `scripts/ingest_fundamentals.py` (one-shot); ships in
  the Docker image (extend the `COPY scripts` already added in Sprint 02).
- **Config** — activate `FUNDAMENTAL_DATA_PROVIDER`, `DEFILLAMA_BASE_URL`,
  optional `DEFILLAMA_API_KEY`, in `config.py` and `.env.example`.
- **Optional enrichment** — populate `assets.category` from the protocol category
  when currently null (an UPDATE, not a schema change).
- **Tests** — provider parsing (fixtures), normalization + missing-data, service
  matching/skip + isolation + run record, `/fundamentals` API, data-quality. Keep
  the full Sprint 01–02 suite and the foundation gate green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (fundamental metric
  definitions), and `docs/api/` (endpoint contract).

## Out of scope

- Tokenomics, risk, divergence, valuation, scoring, technical analysis, reporting,
  notifications, dashboard (Sprint 04+). In particular, **computing divergence**
  between fundamentals and price is Sprint 05 — Sprint 03 only lands the data.
- A background scheduler (APScheduler). Ingestion stays a one-shot command.
- A second fundamental provider, and protocol→multi-token modeling. One protocol
  maps to at most one in-universe asset (via `gecko_id`) this sprint.
- Any change that treats Fees, Revenue, or TVL as interchangeable, or that derives
  one from another. They are distinct, separately-sourced metrics.

## Architecture impact

Adds the **Fundamental Data** module (per the §2 boundary list) and a second
provider adapter, reusing the Sprint 02 provider interface, normalization pattern,
and ingestion infrastructure (`ingestion_runs`, `asset_source_ids`, per-asset
SAVEPOINT). Business logic depends only on `FundamentalDataProvider`; DefiLlama's
shape never leaks past its adapter. Modular monolith preserved (ADR-001); no new
services. If a shared ingestion base is later warranted (two near-identical
services), that refactor is noted as debt — not done speculatively here.

## Data impact

- **No new tables** (reuses `metric_observations`, `asset_source_ids`,
  `ingestion_runs`). If review finds a genuine need, any change will be an
  additive, reversible migration `0003`; the default expectation is **no schema
  change**.
- **Cross-provider identity:** each matched protocol adds a
  `(provider="defillama", external_id=<slug>)` row in `asset_source_ids` pointing
  to the **same** asset that CoinGecko created, joined via `gecko_id`. Symbol is
  never used to match (§13).
- **Metric distinctions preserved (§9):** `fundamental.fees_usd`,
  `fundamental.revenue_usd`, `fundamental.tvl_usd`, and (when supplied)
  `fundamental.holders_revenue_usd` are separate metrics — never summed, averaged,
  or substituted for one another, and never conflated with `market.*` price data.
- **Missing data explicit (ADR-003):** protocols that do not report a metric (many
  report fees but not revenue, or have no TVL) yield `NOT_AVAILABLE`, never `0`.
  The existing check constraint enforces value-present-iff-`OK`.

## API impact

- `GET /fundamentals` — latest `fundamental.*` observation per (asset, metric,
  period), filterable by `asset_id` and/or `metric`. Each item carries `value`,
  `value_status`, `unit`, `period`, `observed_at`, provenance, and `age_seconds`.
  Missing values are represented by `value_status`, never `0`. No stack traces
  leak to consumers (§8, §12). `/assets`, `/market-data`, `/health` unchanged.

## UI impact

None (dashboard deferred to Sprint 10).

## Implementation tasks

1. `FundamentalDataProvider` + `RawFundamentalSnapshot` in `providers/base.py`.
2. `providers/defillama.py` (httpx; fees/revenue + TVL joined by slug; error
   handling); extend `providers/factory.py`.
3. `config.py` + `.env.example` — DefiLlama settings.
4. `fundamentals/normalize.py` — raw → `fundamental.*` observations with explicit
   missing-data and provenance.
5. `fundamentals/service.py` — gecko_id matching to existing assets, defillama
   source-id attach, skip-unmatched, per-asset isolation, run recording; optional
   category enrichment.
6. `fundamentals/repository.py` + `api/routes/fundamentals.py`; register the router.
7. `scripts/ingest_fundamentals.py` — one-shot entrypoint.
8. Tests (unit, integration, API, data-quality); keep prior suites + foundation
   gate green.
9. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
10. Verify end-to-end on Docker + PostgreSQL: ingest market data, then
    fundamentals, and confirm `/fundamentals` returns fees/revenue/TVL with
    unreported metrics as `NOT_AVAILABLE`.

## Testing strategy

- **Unit — provider:** parse a saved DefiLlama fixture (fees/revenue overview +
  protocols/TVL) into `RawFundamentalSnapshot`s; malformed/short payload →
  `MalformedResponse`; 429 → `RateLimited`; transport error → `ProviderUnavailable`.
  HTTP stubbed with `httpx.MockTransport` — no live calls.
- **Unit — normalization:** each field maps to the right `fundamental.*` metric,
  unit, and period; a protocol reporting fees but not revenue yields
  `fees_usd = OK` and `revenue_usd = NOT_AVAILABLE`; nothing becomes `0`.
- **Integration — service (SQLite):** with a pre-seeded CoinGecko asset (gecko_id
  `ethereum`), ingesting a DefiLlama protocol whose `gecko_id = ethereum` attaches
  a `defillama` source id to the **same** asset and writes fundamental
  observations; a protocol with no matching in-universe asset is skipped (counted,
  not created); a per-protocol error is isolated (SAVEPOINT) with no orphan; the
  run is recorded.
- **API:** `/fundamentals` returns the documented shape; a `NOT_AVAILABLE` metric
  is surfaced as status, not `0`; filters by asset and metric work.
- **Data-quality:** no `fundamental.*` observation has `OK` with a null value (or
  vice versa); provenance populated; Fees and Revenue never collapsed to one metric.
- Deterministic and offline (fixtures + `MockTransport`); SQLite for portable runs,
  PostgreSQL via Docker. Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes (new + prior suites);
  `python3 -m unittest tests.test_foundation` still passes.
- Fundamentals ingested from a fixture attach to the correct existing asset via
  `gecko_id`, with fees/revenue/TVL stored as distinct `fundamental.*` metrics and
  missing metrics as explicit `ValueStatus` (never `0`) with full provenance.
- Unmatched protocols are skipped and counted, not force-created (tiered
  processing, §9).
- `GET /fundamentals` returns the ingested data with source and freshness; missing
  values are a status, not `0`.
- Business logic depends only on `FundamentalDataProvider`; no DefiLlama-specific
  shape appears outside `providers/defillama.py` and `fundamentals/normalize.py`.
- `ruff` clean, `mypy` clean; no out-of-scope modules (tokenomics/risk/scoring/etc.)
  introduced; no schema change unless justified and made additive/reversible.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` updated; Sprint 03 report
  completed.
- Release gate (AGENTS.md §7): tests pass → Docker builds → app starts →
  migrations apply → market + fundamentals ingestion and reads work → docs updated
  → release commit → tag `v0.3.0` at the release head.

## Risks

- **Protocol ↔ token identity is genuinely ambiguous** (protocols with no token,
  several tokens, or no CoinGecko listing). Mitigation: match strictly by
  `gecko_id`; skip (do not guess) when there is no unique match; document the
  limitation. Multi-token protocols are out of scope this sprint.
- **Metric confusion (Fees vs Revenue vs Holders Revenue).** Mitigation: distinct
  metric names, unit/period recorded, data-quality test asserting they are never
  merged; never derive one from another.
- **DefiLlama API shape / unit drift, undocumented nulls.** Mitigation: validate at
  the boundary, snapshot fixtures, explicit missing-data.
- **Rate limits / free-tier.** Mitigation: 429 → `RateLimited`, configurable
  timeout, few broad calls (overview + protocols), tests never hit the network.
- **Scope creep into divergence/scoring.** Mitigation: Sprint 03 lands data only;
  divergence is Sprint 05.

## Rollback considerations

Sprint 03 is expected to add **no schema change** — the new modules are additive
and inert until `scripts/ingest_fundamentals.py` is run, so `/health`, `/assets`,
and `/market-data` are unaffected. Fundamentals are stored as ordinary
`metric_observations`; to remove them, delete rows where `metric LIKE 'fundamental.%'`
(no structural change). If a justified additive migration `0003` is introduced, it
ships with a working `downgrade()`. `git checkout v0.2.0` returns to the market-data
foundation; `v0.2.0` remains the prior stable anchor and `v0.3.0` becomes the next.
