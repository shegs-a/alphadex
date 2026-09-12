# Sprint 03 Report — Fundamental Intelligence

## Sprint objective

Add the second data domain — protocol fundamentals — behind a
`FundamentalDataProvider` interface, with DefiLlama as the first provider. Fetch
fees, revenue, holders-revenue, and TVL, match protocols to assets already in the
universe by `gecko_id` (Phase 1), normalize into distinct `fundamental.*`
observations with explicit missing-data and provenance, and expose a read-only
`/fundamentals` endpoint — all exercised by deterministic, offline tests.

## Completed tasks

- **Provider abstraction** (`src/alphadex/providers/`): `FundamentalDataProvider`
  interface + `RawFundamentalSnapshot` DTO (reusing the `ProviderError` hierarchy);
  `DefiLlamaProvider` assembling TVL (`/protocols`) with fees/revenue/holders-
  revenue (`/overview/fees` variants) joined by slug, deduplicated by `gecko_id`
  (largest-TVL representative); holders-revenue fetched best-effort (logged, not
  fatal). Factory extended with `build_fundamental_data_provider`.
- **Fundamental Data + Normalization** (`src/alphadex/fundamentals/`): `normalize`
  (raw → distinct `fundamental.*` metrics with units/periods; absent → explicit
  `ValueStatus`, never `0`); `service.FundamentalDataService` (Phase 1 gecko_id
  match to existing assets, skip+count unmatched, attach `defillama` source id,
  optional category enrichment, per-asset SAVEPOINT isolation, `ingestion_runs`
  record); `repository.latest_fundamentals`.
- **API**: read-only `GET /fundamentals`; the market repository is now scoped to
  the `market.*` namespace so `/market-data` and `/fundamentals` never overlap.
- **Ops**: `scripts/ingest_fundamentals.py` one-shot ingestion (ships in the image
  via the existing `COPY scripts`).
- **Config**: `fundamental_data_provider`, `defillama_base_url`, optional
  `defillama_api_key`; `.env.example` updated.
- **Tests** (+20): DefiLlama provider (assembly, dedupe, missing-data, holders-
  revenue degradation, error modes) via `httpx.MockTransport`; normalization +
  missing-data; ingestion service (match, skip, enrichment, append-only,
  isolation, run record); `/fundamentals` API incl. domain separation.
- **Docs**: README (status/capabilities/setup), CHANGELOG (`0.3.0`), `docs/data/`
  (fundamental metric definitions + matching), `docs/api/` (`/fundamentals`), this
  report.

## Incomplete tasks

None within scope. Creating assets for unmatched protocols, a second fundamentals
provider, and a background scheduler were explicitly out of scope (deferred).

## Files/modules changed

New: `src/alphadex/providers/defillama.py`,
`src/alphadex/fundamentals/{__init__,normalize,service,repository}.py`,
`src/alphadex/api/routes/fundamentals.py`, `scripts/ingest_fundamentals.py`,
`tests/{test_providers_defillama,test_fundamentals_normalize,
test_fundamentals_service,test_api_fundamentals}.py`,
`docs/sprints/sprint-03-plan.md`, this report.
Modified: `src/alphadex/providers/{base,__init__,factory}.py`,
`src/alphadex/config.py`, `src/alphadex/api/app.py`,
`src/alphadex/marketdata/repository.py` (market.* scoping), `README.md`,
`CHANGELOG.md`, `.env.example`, `docs/data/README.md`, `docs/api/README.md`.

## Database changes

**None.** Fundamentals reuse `metric_observations` (under the `fundamental.*`
namespace), `asset_source_ids` (a `defillama` mapping added to the matched asset),
and `ingestion_runs`. No migration was required, as anticipated by the plan.

## API changes

Added read-only `GET /fundamentals` (latest `fundamental.*` observation per
asset/metric/period, with `value_status`, provenance, and `age_seconds`).
`/market-data` now returns only `market.*` metrics (previously it would have
returned any latest observation, including `fundamental.*`). `/health`, `/assets`
unchanged. OpenAPI docs at `/docs` reflect the new route.

## Configuration changes

`.env.example` activates `FUNDAMENTAL_DATA_PROVIDER`, `DEFILLAMA_BASE_URL`, and
optional `DEFILLAMA_API_KEY`. No secrets committed.

## Tests executed

```
uv run pytest                              # full suite
uv run ruff check .                        # lint
uv run ruff format --check .               # format
uv run mypy src                            # type check
python3 -m unittest tests.test_foundation  # dependency-free gate
docker compose up --build                  # container path (PostgreSQL 16)
docker compose exec app python scripts/ingest_market_data.py --top-n 100
docker compose exec app python scripts/ingest_fundamentals.py
```

## Test results

- **pytest: 63 passed** (43 prior + 20 new: DefiLlama provider 6, normalization 4,
  service 7, API 3).
- **ruff: all checks passed; format clean. mypy: success (25 source files).**
- **Foundation gate: 7 passed.**
- **End-to-end (Docker + PostgreSQL 16, live DefiLlama):** ingested the top-100
  market universe, then fundamentals — **2,367 protocols fetched, 35 matched by
  `gecko_id`, 2,332 skipped, 0 failed, 315 observations** written. `/fundamentals`
  returned real fees/revenue/TVL (19/35 assets with fees, 16 with revenue, 11 with
  TVL) with unreported metrics as `NOT_AVAILABLE` — never `0` — and the four
  metrics kept distinct.

## Bugs discovered / fixed

- **`/market-data` domain leak (found by an API test, fixed before commit):** with
  two domains sharing `metric_observations`, the market read query returned any
  latest observation — including `fundamental.*` rows. Scoped the market repository
  query to the `market.*` namespace; `/fundamentals` is scoped to `fundamental.*`.

## Known limitations

- **Phase 1 matching by `gecko_id` only.** Fundamentals exist only for assets in
  the market universe; protocols with no match (or no `gecko_id`) are skipped and
  counted. Broadening coverage (creating assets for unmatched protocols, handling
  protocols with no/multiple tokens) is deferred to a later version.
- **Multi-protocol tokens** are represented by their largest-TVL protocol
  (dedupe rule) to avoid double-counting; other protocols sharing a `gecko_id` in a
  run are ignored. This is a deliberate Phase 1 simplification.
- **Skipped count is not persisted** in `ingestion_runs` (only `assets_ok`,
  `assets_failed`, `observations_written`); it is surfaced in logs and the run
  summary. A dedicated column can be added later if needed.
- No tokenomics/scoring/divergence yet (Sprint 04+); divergence between
  fundamentals and price is Sprint 05. Synchronous provider/DB access.

## Technical debt

- `MarketDataService` and `FundamentalDataService` share a near-identical ingestion
  shape (run record, per-asset SAVEPOINT, summary). A shared ingestion base could
  reduce duplication once a third provider lands — deferred to avoid premature
  abstraction.
- DefiLlama slug↔protocol join relies on the overview `slug` matching `/protocols`
  `slug`; entries that don't align are simply not enriched (no fees/revenue). Add a
  reconciliation report if coverage gaps matter.
- Provider retry/backoff remains minimal (errors surfaced, not retried).

## Deviations from the plan

- None material. The plan anticipated "no schema change"; confirmed. The
  `/market-data` namespace scoping was an additional correctness fix surfaced by the
  domain-separation test (see Bugs).

## Architecture decisions

No new ADRs. Implements ADR-001 (modular monolith — new Fundamental Data module and
second provider), ADR-002 (stack — httpx provider, no new deps), ADR-003 (explicit
missing-data through normalization + the check constraint), ADR-004 (append-only
observations). Provider abstraction and metric distinctions per AGENTS.md §2/§9/§13.
Phase-1 `gecko_id` matching recorded in `docs/sprints/sprint-03-plan.md`.

## Release/version created

- Version: **v0.3.0** (fundamental intelligence, container-verified).
- Commit: release commit on branch `claude/resume-session-devices-ibdww4`.
- Tag/Release: annotated tag `v0.3.0` at the release head, pushed to origin, and a
  GitHub Release published from it via `gh`.

## Rollback procedure

- No schema to revert. To remove fundamentals data, delete `metric_observations`
  rows where `metric LIKE 'fundamental.%'` and `asset_source_ids` rows where
  `provider = 'defillama'` (no structural change). The new modules are inert until
  `scripts/ingest_fundamentals.py` runs, so `/health`, `/assets`, and `/market-data`
  are unaffected.
- `git checkout v0.2.0` returns to the market-data foundation. `v0.2.0` remains the
  prior stable anchor; `v0.3.0` becomes the new one.

## Recommended next steps (Sprint 04 — Opportunity Scanner)

1. Define the screening pass over the universe using market + fundamental
   observations (cheap broad screen → candidates), per the tiered pipeline (§9).
2. Introduce configurable screen thresholds (in config, not hard-coded) and emit a
   ranked candidate list behind a read endpoint.
3. Keep signals evidence-backed and explainable; no blind BUY language (§10).
4. Prepare the inputs the Divergence Engine (Sprint 05) will consume (fundamentals
   trend vs price trend), without computing divergence yet.
