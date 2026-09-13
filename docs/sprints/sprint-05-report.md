# Sprint 05 Report — Economic Divergence Engine

## Sprint objective

Build the heart of the thesis: detect and quantify where a protocol's fundamentals
are improving faster than the market's price/valuation recognizes. For the Scanner's
candidates, compute fundamentals and price/valuation trends, measure the gap,
classify the divergence, and persist an explainable signal (§10). Expose results via
read-only `/divergences`.

## Completed tasks

- **Divergence module** (`src/alphadex/divergence/`): `config` (validated
  `DivergenceConfig`); `inputs` (`AssetSeries`/`ObsPoint`, present values only);
  `trends` (Track A provider growth-window acceleration + Track B cross-time from the
  append-only history, preferred when available; a coarse market-cap-to-fees
  multiple as one input, with explicit "unavailable" results — never `0`); `engine`
  (signed divergence score in [-1, 1] — a component, not the Alpha Score;
  classification; §10 evidence assembly; missing core input → `null`); `service`
  (`DivergenceService` — candidate selection per §9, per-asset SAVEPOINT isolation,
  ranking, run record); `repository`.
- **Persistence** (migration `0004`, additive/reversible): `divergence_runs` (config
  snapshot, counts, timing) and `divergence_signals` (typed
  trends/score/method/data_quality + JSON evidence). ORM models `DivergenceRun`,
  `DivergenceSignal`.
- **API**: read-only `GET /divergences` (ranked, filter by classification),
  `GET /divergences/{asset_id}` (404 if not analyzed), `GET /divergence-runs`.
- **Ops**: `scripts/run_divergence.py` one-shot pass.
- **Config**: scope (candidates/all), min-history, classification thresholds, and
  divergence score component weights; `.env.example` updated.
- **Tests** (+25): config validation, trends (Track A/B, insufficient→None,
  valuation multiple), engine (score/classification/evidence/no-inflation/no-BUY),
  service (persist/rank/scope/isolation/history), API. Migration test extended for
  `0004`.
- **Docs**: README, CHANGELOG (`0.5.0`), `docs/data/` (divergence entities +
  method), `docs/api/` (`/divergences`), this report.

## Incomplete tasks

None within scope. Valuation/risk/alpha scoring, tokenomics, technical setup,
reporting, notifications, dashboard, and automated ingestion cadence (a scheduler)
are later sprints.

## Files/modules changed

New: `src/alphadex/divergence/{__init__,config,inputs,trends,engine,service,
repository}.py`, `src/alphadex/api/routes/divergences.py`,
`migrations/versions/0004_divergence.py`, `scripts/run_divergence.py`,
`tests/{test_divergence_config,test_divergence_trends,test_divergence_engine,
test_divergence_service,test_api_divergences}.py`, `docs/sprints/sprint-05-plan.md`,
this report.
Modified: `src/alphadex/models.py` (DivergenceRun/DivergenceSignal),
`src/alphadex/config.py` (divergence settings), `src/alphadex/api/app.py` (router),
`tests/test_migration.py`, `README.md`, `CHANGELOG.md`, `.env.example`,
`docs/data/README.md`, `docs/api/README.md`.

## Database changes

Migration `0004` (additive, on top of `0003`): `divergence_runs` and
`divergence_signals` (`divergence_run_id` FK, `asset_id` FK, `classification`,
nullable `divergence_score`/trends/`data_quality`, `window`, `method`, `rank`, JSON
`evidence`; `UNIQUE(divergence_run_id, asset_id)` + indexes). Sprints 01–04 schema
untouched. Signals are derived data.

## API changes

Added read-only `GET /divergences`, `GET /divergences/{asset_id}`,
`GET /divergence-runs`. Prior endpoints unchanged. OpenAPI docs at `/docs` reflect
the new routes.

## Configuration changes

`.env.example` adds the divergence block: `DIVERGENCE_SCOPE`,
`DIVERGENCE_MIN_HISTORY_DAYS`, `DIVERGENCE_THRESHOLD`,
`DIVERGENCE_WEAKENING_THRESHOLD`, `DIVERGENCE_MIN_FUNDAMENTALS_IMPROVEMENT`, and
`DIVERGENCE_WEIGHT_GAP`/`_VALUATION` (validated to sum to 1.0). No secrets.

## Tests executed

```
uv run pytest                              # full suite
uv run ruff check .                        # lint
uv run ruff format --check .               # format
uv run mypy src                            # type check
python3 -m unittest tests.test_foundation  # dependency-free gate
docker compose up --build                  # container path (PostgreSQL 16)
docker compose exec app python scripts/run_divergence.py
```

## Test results

- **pytest: 114 passed** (89 prior + 25 new: config 4, trends 7, engine 5,
  service 4, API 5). ruff clean; format clean; **mypy: success (41 source files)**;
  foundation gate 7 passed.
- **End-to-end (Docker + PostgreSQL 16):** migration `0004` applied; a pass over the
  scan's **91** candidates+watch produced **2 fundamental_divergence / 8 watch /
  8 thesis_weakening / 73 insufficient_data**, 0 failed. `/divergences` returned
  ranked, caveated signals — e.g. one flagged asset carried "price already moved" as
  an explicit contradiction and a low `data_quality` (0.3, single-snapshot). The 73
  insufficient_data assets (no fundamentals) correctly produced no divergence claim.

## Bugs discovered / fixed

- None new. mypy/ruff issues (unused import, missing annotations on the evidence
  builder, import ordering) were fixed during development before commit.

## Known limitations

- **Track A dominates until history accrues.** With mostly single snapshots, most
  signals use `growth_window` (data_quality ~0.3). Track B engages automatically per
  asset as observations accumulate; building history is manual for now (scheduler is
  Sprint 12).
- **Coarse valuation multiple.** Market-cap-to-fees is a divergence input only, not a
  valuation verdict (Sprints 06–07).
- **Acceleration proxy caveats.** Fee-run-rate acceleration can be noisy or
  incentive-driven; the engine surfaces this in `major_risk` rather than hiding it.
- A component only — no Alpha/Risk/Confidence trio yet (Sprint 07). Synchronous
  DB access.

## Technical debt

- `MarketDataService`, `FundamentalDataService`, `ScanService`, and
  `DivergenceService` now share a run-record + summary + isolation shape; a common
  base is increasingly justified and should be extracted soon.
- Divergence reads per-asset history with a single bulk query then computes in
  Python; fine at current scale, revisit if the analyzed set grows large.
- Default thresholds/weights are sensible but not empirically tuned (deliberately —
  no hindsight bias, §10); revisit with backtesting (Sprint 11).

## Deviations from the plan

- None. Implemented both tracks as planned; deferred history automation as decided
  (option 1); no schema surprises (migration `0004` as planned).

## Architecture decisions

No new ADRs. Adds the Divergence Engine module (§2) following the established
analytical-layer pattern (config-driven, explainable, persisted with evidence).
Honors ADR-003 (missing → `null`, never `0`), ADR-004 (reads the append-only
history; Track B keys off `observed_at`; signals are derived), and §9/§10 (tiered
pipeline, component not verdict, explainability, no blind BUY, no hindsight bias).

## Release/version created

- Version: **v0.5.0** (economic divergence engine, container-verified).
- Commit: release commit on branch `claude/resume-session-devices-ibdww4`.
- Tag/Release: annotated tag `v0.5.0` at the release head, pushed to origin, and a
  GitHub Release published from it via `gh`.

## Rollback procedure

- `alembic downgrade -1` drops `divergence_runs` and `divergence_signals`
  (Sprints 01–04 schema untouched). Signals are derived data — regenerable by
  re-running the engine — so dropping them loses no source information. The engine is
  read-only over existing observations/scan results, so ingestion, scan, and read
  paths are unaffected.
- `git checkout v0.4.0` returns to the Scanner foundation. `v0.4.0` remains the
  prior stable anchor; `v0.5.0` becomes the new one.

## Recommended next steps (Sprint 06 — Tokenomics & Risk Engine)

1. Model **token value capture** (does protocol strength actually accrue to the
   token: emissions, supply schedule, fee-to-holders) — turning the coarse multiple
   into a real signal.
2. Build the **Risk Engine** (liquidity, concentration, volatility, data-quality,
   contract/counterparty risk) as a separate output — a high divergence with
   unacceptable risk is not a top candidate (§10).
3. Keep both explainable and config-driven; feed them toward the Alpha Scoring
   engine (Sprint 07), which combines divergence + value capture + risk into the
   three separate outputs (Alpha, Risk, Confidence).
