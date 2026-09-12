# Sprint 04 Plan — Opportunity Scanner

## Objective

Build the **first analytical pass**: a configurable, explainable **screen** that
evaluates every asset in the universe against inclusion criteria using the
market and fundamental observations already ingested, narrows the universe to a
ranked **candidate** set, and persists each scan with the evidence behind every
decision. Expose the results through a read-only `/opportunities` endpoint and a
`scripts/run_scan.py` command. This is the cheap, broad **top of the tiered
pipeline** (AGENTS.md §9) — it decides *what deserves deeper analysis*, not the
final verdict.

## Problem being solved

Sprints 02–03 fill the database with market and fundamental data for the whole
universe, but nothing yet *reduces* that universe to things worth a human's (or a
deeper engine's) attention. Running expensive divergence/valuation/risk analysis on
every asset is wasteful and noisy (§9). The Scanner is the funnel entrance: a
transparent, configurable first filter that flags candidates and — crucially —
records *why* each asset passed or failed, so later sprints (Divergence,
Valuation, Risk, Alpha Scoring) operate on a principled shortlist and every result
is explainable and backtestable.

## What this sprint is NOT

To keep boundaries sharp (this is the sprint most at risk of scope creep):

- **Not the Alpha Score.** The Scanner emits a coarse, preliminary **Screen Score**
  for ordering candidates only. The real Alpha Score / Risk Score / Confidence —
  three separate outputs — are Sprint 07.
- **Not the Divergence Engine** (Sprint 05). The screen uses cheap, single-snapshot
  signals; it does not compute fundamentals-vs-price divergence or trends over time.
- **Not the Valuation or Risk engines** (Sprints 06–07). Any ratio used here is a
  coarse screening heuristic, explicitly labeled as such — not a valuation verdict.
- **No blind BUY signals** (§10). Outputs use `candidate`, `watch`,
  `insufficient_data`, `excluded` — never `BUY`, `GUARANTEED`, `100% PUMP`.

## Scope

- **Screen module** (`src/alphadex/scanner/`)
  - `criteria.py` — the configurable inclusion **gates**, each a small pure
    function over an asset's latest observations returning pass/fail **plus the
    value and threshold considered** (for explainability). Missing data is handled
    explicitly: an asset lacking a required input is flagged `insufficient_data`,
    **never scored as if the value were `0`** (ADR-003).
  - `score.py` — a transparent, **configurable weighted Screen Score** over a few
    normalized cheap signals (e.g. fundamentals presence/magnitude, liquidity,
    recent price change). Weights and thresholds come from config, never hard-coded
    (§2, §10). Assets with incomplete data get a Screen Score **and** an explicit
    completeness flag — poor data never masquerades as a strong signal.
  - `service.py` — `ScanService`: load the universe's latest market + fundamental
    observations, evaluate criteria + score per asset, classify
    (`candidate` / `watch` / `insufficient_data` / `excluded`), rank candidates, and
    persist a `scan_run` with per-asset `scan_results`.
  - `repository.py` — read the latest scan and its ranked results.
- **Persistence** (migration `0003`, additive/reversible)
  - `scan_runs` — one row per scan: timestamp, status, a snapshot of the config
    used (thresholds/weights), universe size, candidate count.
  - `scan_results` — per asset: `scan_run_id`, `asset_id`, `status`, `passed`,
    `screen_score` (nullable), `rank`, `data_completeness`, and a `reasons` JSON
    breakdown (per-criterion pass/fail with value+threshold — explanatory metadata,
    §9). Core decision fields are typed columns; JSON holds only the human-readable
    breakdown.
- **Read API**
  - `GET /opportunities` — ranked candidates from the latest scan (asset, status,
    screen score, completeness, the criteria evidence). Filterable by status.
  - `GET /opportunities/{asset_id}` — one asset's latest scan result with full
    reasons; `404` if it was not scanned.
  - `GET /scans` — recent scan runs (metadata + counts).
- **Command** — `scripts/run_scan.py` (one-shot; runs a scan over the current data).
- **Config** — a configurable screen definition in `config.py` / `.env.example`:
  universe filters (market-cap floor/ceiling, minimum 24h volume), data-freshness
  window, minimum fundamentals presence, and Screen Score weights (summing to 1.0,
  validated).
- **Tests** — criteria (each gate, incl. explicit missing-data), scoring
  (deterministic, weight config, incomplete-data handling), scan service
  (classification, ranking, persistence, no-fundamentals path), API, config
  validation. Keep all prior suites + the foundation gate green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (scan entities), `docs/api/`
  (`/opportunities`, `/scans`).

## Out of scope

- Divergence, valuation, risk, alpha scoring, technical setup, tokenomics
  (Sprints 05–08). A background scheduler and notifications (Sprints 09+).
- New data providers or ingestion changes. The Scanner is a **read-only consumer**
  of existing observations; it fetches nothing external.
- Any signal requiring historical trend across scans (uses the latest snapshot
  only this sprint). Trend/divergence is Sprint 05.
- Tuning thresholds against today's winners — **no hindsight bias** (§10). Defaults
  are sensible and documented, not fitted to known outcomes.

## Architecture impact

Adds the **Opportunity Scanner** module (per the §2 boundary list) — a pure
analytical layer that depends only on the internal data model
(`metric_observations`), never on providers or the scoring engine. It reads
normalized observations and writes scan results; it introduces the pattern later
analytical engines (Divergence, Valuation, Risk, Scoring) will follow: config-driven,
explainable, persisted with evidence. Modular monolith preserved (ADR-001).

## Data impact

- **New (migration `0003`, additive):** `scan_runs` and `scan_results`
  (see Scope). `scan_results.screen_score` is nullable and, when absent, carries a
  status explaining why (e.g. `insufficient_data`) — never a `0` standing in for
  "unknown" (ADR-003). Config used for a scan is snapshotted on `scan_runs` for
  auditability and backtestability (§ ADR-004 spirit: results are reproducible from
  recorded inputs).
- **Reused unchanged:** `assets`, `metric_observations`, `asset_source_ids`,
  `ingestion_runs`. The Scanner reads the latest `market.*` and `fundamental.*`
  observations per asset.
- **Missing data stays explicit:** an asset with market data but no fundamentals is
  a first-class case — classified with a completeness flag and either held as
  `watch`/`insufficient_data` per config, never silently treated as zero-fundamentals.

## API impact

- `GET /opportunities` — ranked candidates from the latest scan; each item exposes
  its Screen Score, status, data completeness, and the per-criterion evidence
  (why included / what supports / the major data gap). No BUY language (§10).
- `GET /opportunities/{asset_id}` — one asset's latest result with full reasons;
  `404` if not scanned.
- `GET /scans` — recent scan runs with counts. `/health`, `/assets`,
  `/market-data`, `/fundamentals` unchanged. No stack traces leak (§8, §12).

## UI impact

None (dashboard deferred to Sprint 10). The `/opportunities` JSON is the first
"results" surface a human or the future dashboard will consume.

## Implementation tasks

1. `scanner/criteria.py` — configurable gates over latest observations, each
   returning pass/fail + value + threshold; explicit missing-data.
2. `scanner/score.py` — configurable weighted Screen Score + completeness flag.
3. Migration `0003` — `scan_runs`, `scan_results`; verify upgrade/downgrade.
4. `scanner/service.py` — evaluate, classify, rank, persist a scan run.
5. `scanner/repository.py` + `api/routes/opportunities.py` (+ `/scans`); register.
6. `scripts/run_scan.py` — one-shot scan entrypoint.
7. `config.py` + `.env.example` — screen thresholds + weights (validated to 1.0).
8. Tests (criteria, scoring, service, API, config); keep prior suites + foundation
   gate green.
9. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
10. Verify end-to-end on Docker + PostgreSQL: ingest market + fundamentals, run a
    scan, and confirm `/opportunities` returns a ranked, explainable candidate list
    with incomplete-data assets correctly flagged (not zero-scored).

## Testing strategy

- **Unit — criteria:** each gate passes/fails at its threshold; an asset missing a
  required observation is flagged `insufficient_data`, not evaluated as `0`; the
  returned evidence records the value and threshold used.
- **Unit — scoring:** the Screen Score is a deterministic function of the
  configured weights; changing a weight changes the score predictably; an
  incomplete-data asset is scored with its completeness flag set and never
  out-ranks a complete asset purely because a missing input read as favorable.
- **Integration — service (SQLite):** seeded market + fundamental observations
  produce a `scan_run` with `scan_results`; candidates are ranked; an asset with no
  fundamentals is classified per config; re-running creates a new scan (history
  preserved), leaving prior scans intact.
- **API:** `/opportunities` returns ranked candidates with evidence and status;
  filter by status works; `/opportunities/{id}` `404` for an unscanned asset;
  `/scans` lists runs. No forbidden BUY language appears in any field.
- **Config:** Screen Score weights are validated (must sum to 1.0); invalid config
  is rejected with a clear error.
- Deterministic; SQLite for portable runs, PostgreSQL via Docker/migration.
  Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes (new + prior suites);
  `python3 -m unittest tests.test_foundation` still passes.
- `alembic upgrade head` applies `0003` (and `downgrade` reverses it), creating
  `scan_runs` + `scan_results`.
- A scan over seeded data persists a run and ranked results with per-criterion
  evidence; assets with incomplete data are flagged, **never zero-scored**.
- Screen thresholds and weights are read from config (validated), not hard-coded;
  the config used is snapshotted on the scan run.
- `GET /opportunities` returns explainable, ranked candidates; no BUY/GUARANTEED
  language anywhere (§10).
- Scanner depends only on the internal data model — no provider or scoring-engine
  coupling. `ruff` clean, `mypy` clean; no out-of-scope engines introduced.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` updated; Sprint 04 report
  completed.
- Release gate (AGENTS.md §7): tests pass → Docker builds → app starts →
  migrations apply → ingest + scan + read workflow works → docs updated → release
  commit → tag `v0.4.0` at the release head.

## Risks

- **Scope creep into valuation/divergence/scoring.** Mitigation: the "What this
  sprint is NOT" section; Screen Score is explicitly preliminary; ratios are
  labeled screening heuristics; no cross-time or vs-price computation.
- **Missing data treated as `0`** (the classic failure). Mitigation: criteria and
  scoring handle absence explicitly with a completeness flag; a dedicated test
  asserts incomplete assets are never zero-scored or falsely ranked.
- **Hindsight bias / over-fitted thresholds** (§10). Mitigation: defaults are
  documented, general, and config-overridable; no fitting to known winners.
- **JSON `reasons` sprawl.** Mitigation: typed columns for all decision fields;
  JSON holds only the human-readable per-criterion breakdown (§9).

## Rollback considerations

Migration `0003` is additive with a working `downgrade()`: `alembic downgrade -1`
drops `scan_runs` and `scan_results` (Sprints 01–03 schema untouched). Scan results
are **derived data** — regenerable by re-running a scan — so dropping them loses no
source information. The Scanner is read-only over existing observations, so the
ingestion and read paths are unaffected. `git checkout v0.3.0` returns to the
fundamentals foundation; `v0.3.0` remains the prior stable anchor and `v0.4.0`
becomes the next once tagged.
