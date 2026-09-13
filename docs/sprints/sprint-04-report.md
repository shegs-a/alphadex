# Sprint 04 Report — Opportunity Scanner

## Sprint objective

Build the first analytical pass: a configurable, explainable screen over the market
and fundamental observations already ingested that narrows the universe to a ranked
candidate set and persists each scan with the evidence behind every decision.
Expose results via read-only `/opportunities` and `/scans`. The Scanner is the cheap,
broad top of the tiered pipeline (§9) — it decides what deserves deeper analysis,
not the final verdict.

## Completed tasks

- **Scanner module** (`src/alphadex/scanner/`): `inputs` (`ObsValue`/`AssetSnapshot`
  — missing data explicit, never `0`); `config` (validated `ScreenConfig`, weights
  must sum to 1.0); `criteria` (inclusion gates returning pass/fail + value +
  threshold); `score` (preliminary Screen Score — log-scaled activity/liquidity/
  momentum blend; a missing signal lowers completeness and never inflates);
  `service.ScanService` (classify, rank scored results, persist a run); `repository`
  (snapshot loader + read queries).
- **Persistence** (migration `0003`, additive/reversible): `scan_runs` (config
  snapshot, counts, timing) and `scan_results` (typed decision fields —
  `status`/`passed`/`screen_score`/`rank`/`data_completeness` — plus a JSON
  `reasons` breakdown). ORM models `ScanRun`, `ScanResult`.
- **API**: read-only `GET /opportunities` (ranked, filter by status),
  `GET /opportunities/{asset_id}` (404 if unscanned), `GET /scans`.
- **Ops**: `scripts/run_scan.py` one-shot scanner.
- **Config**: gates (market-cap floor/ceiling, min volume, freshness,
  require-fundamentals), normalization references, and Screen Score weights;
  `.env.example` updated.
- **Tests** (+26): config validation, criteria (incl. missing-data gates), score
  (completeness, no inflation, weight behaviour), service (classification, ranking,
  persistence, insufficient-data, history), API (evidence, status filter,
  null-score, `404`, no-BUY-language). Migration test extended for `0003`.
- **Docs**: README, CHANGELOG (`0.4.0`), `docs/data/` (scan entities + screen),
  `docs/api/` (`/opportunities`, `/scans`), this report.

## Incomplete tasks

None within scope. Divergence, valuation, risk, the real Alpha/Risk/Confidence
scoring, a scheduler, and notifications are later sprints.

## Files/modules changed

New: `src/alphadex/scanner/{__init__,inputs,config,criteria,score,service,
repository}.py`, `src/alphadex/api/routes/opportunities.py`,
`migrations/versions/0003_scan_results.py`, `scripts/run_scan.py`,
`tests/{test_scanner_config,test_scanner_criteria,test_scanner_score,
test_scanner_service,test_api_opportunities}.py`,
`docs/sprints/sprint-04-plan.md`, this report.
Modified: `src/alphadex/models.py` (ScanRun/ScanResult), `src/alphadex/config.py`
(scan settings), `src/alphadex/api/app.py` (router), `tests/test_migration.py`,
`README.md`, `CHANGELOG.md`, `.env.example`, `docs/data/README.md`,
`docs/api/README.md`.

## Database changes

Migration `0003` (additive, on top of `0002`): `scan_runs` (status, timing,
`universe_size`, `candidate_count`, JSON `config`, error) and `scan_results`
(`scan_run_id` FK, `asset_id` FK, `status`, `passed`, `screen_score` nullable,
`rank` nullable, `data_completeness` nullable, JSON `reasons`;
`UNIQUE(scan_run_id, asset_id)` + indexes). Sprints 01–03 schema untouched. Scan
results are derived data.

## API changes

Added read-only `GET /opportunities`, `GET /opportunities/{asset_id}`, `GET /scans`.
`/health`, `/assets`, `/market-data`, `/fundamentals` unchanged. OpenAPI docs at
`/docs` reflect the new routes.

## Configuration changes

`.env.example` adds the scanner block: `SCAN_MARKET_CAP_MIN`/`_MAX`,
`SCAN_MIN_VOLUME_24H`, `SCAN_FRESHNESS_MAX_HOURS`, `SCAN_REQUIRE_FUNDAMENTALS`,
`SCAN_REF_FEES_30D`, `SCAN_REF_VOLUME_24H`, and `SCAN_WEIGHT_ACTIVITY`/`_LIQUIDITY`/
`_MOMENTUM` (validated to sum to 1.0). No secrets.

## Tests executed

```
uv run pytest                              # full suite
uv run ruff check .                        # lint
uv run ruff format --check .               # format
uv run mypy src                            # type check
python3 -m unittest tests.test_foundation  # dependency-free gate
docker compose up --build                  # container path (PostgreSQL 16)
docker compose exec app python scripts/run_scan.py
```

## Test results

- **pytest: 89 passed** (63 prior + 26 new: config 4, criteria 8, score 4,
  service 4, API 6).
- **ruff: all checks passed; format clean. mypy: success (33 source files).**
- **Foundation gate: 7 passed.**
- **End-to-end (Docker + PostgreSQL 16):** migration `0003` applied; a scan over the
  ingested universe (100 assets, fundamentals for 35) produced **19 candidates /
  72 watch / 9 excluded / 0 insufficient**; `/opportunities` returned ranked
  candidates (SOL #1 0.918, JUP, BTC, …) with full gate + signal evidence, and
  excluded illiquid assets (LEO, BUIDL) with `screen_score = null`.

## Bugs discovered / fixed

- None new in this sprint's code. (The `/market-data` domain-scoping fix that made
  the namespaces clean was landed in Sprint 03; the Scanner relies on it.)

## Known limitations

- The Screen Score is a **preliminary** ordering heuristic, deliberately thin: no
  valuation ratios, no cross-time/vs-price signals (those are the Divergence,
  Valuation, and Alpha Scoring engines, Sprints 05–07).
- Single-snapshot only — the screen uses the latest observation per metric, not
  trends across scans.
- Momentum uses a linear −50%…+50% mapping; extreme moves saturate. Tunable later.
- No scheduler: scans are run on demand. Synchronous DB access.

## Technical debt

- `MarketDataService`, `FundamentalDataService`, and now `ScanService` share a
  run-record + summary shape; a shared base could reduce duplication once a fourth
  such flow lands. Deferred to avoid premature abstraction.
- Default thresholds/weights are sensible but not empirically tuned (deliberately —
  no hindsight bias, §10); revisit with backtesting (Sprint 11).

## Deviations from the plan

- None. Implemented the "thin screen" option as decided; no schema surprises
  (migration `0003` as planned).

## Architecture decisions

No new ADRs. Adds the Opportunity Scanner module (§2) as a pure analytical layer
over the internal data model — the pattern (config-driven, explainable, persisted
with evidence) that later engines will follow. Honors ADR-003 (missing data never
`0`), ADR-004 (reads the append-only history; scan results are derived), and §9/§10
(tiered pipeline, separate/preliminary scoring, no blind BUY).

## Release/version created

- Version: **v0.4.0** (opportunity scanner, container-verified).
- Commit: release commit on branch `claude/resume-session-devices-ibdww4`.
- Tag/Release: annotated tag `v0.4.0` at the release head, pushed to origin, and a
  GitHub Release published from it via `gh`.

## Rollback procedure

- `alembic downgrade -1` drops `scan_runs` and `scan_results` (Sprints 01–03 schema
  untouched). Scan results are derived data — regenerable by re-running a scan — so
  dropping them loses no source information. The Scanner is read-only over existing
  observations, so ingestion and read paths are unaffected.
- `git checkout v0.3.0` returns to the fundamentals foundation. `v0.3.0` remains the
  prior stable anchor; `v0.4.0` becomes the new one.

## Recommended next steps (Sprint 05 — Economic Divergence Engine)

1. Compute divergence between improving fundamentals and lagging price/valuation,
   using the append-only history (fundamentals trend vs price trend over time).
2. Persist divergence signals with evidence (what changed, why now, what supports/
   contradicts/invalidates) — feeding the candidate set the Scanner produces.
3. Add read endpoints for divergences; keep signals explainable and free of blind
   BUY language (§10).
4. Begin capturing periodic snapshots (or document the ingestion cadence) so trends
   have history to work with.
