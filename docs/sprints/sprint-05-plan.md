# Sprint 05 Plan — Economic Divergence Engine

## Objective

Build the **heart of the thesis**: detect and quantify where a protocol's economic
fundamentals are improving materially **faster than the market's price/valuation is
recognizing**. For each asset (prioritizing the Scanner's candidates), compute a
fundamentals trend and a price/valuation trend, measure the **gap** between them,
classify the divergence, and persist an explainable signal (what changed, why now,
what supports/contradicts/invalidates it, the major risk). Expose results through a
read-only `/divergences` endpoint. This turns raw data into the system's first real
*insight*.

## Problem being solved

Sprints 02–04 give us data and a screened candidate list, but nothing yet answers
the actual question AlphaDex exists to answer (§1): *is economic activity improving
faster than price is pricing in?* The Divergence Engine is that computation. It must
carefully separate the four things AGENTS.md refuses to conflate — a protocol
getting stronger, the token capturing that, the token being cheap, and an entry
existing — and here we focus on the **first two vs. price**: fundamentals improving
while price/valuation lags.

## The history problem (read this first)

Divergence is inherently a statement about **change over time**, but the database so
far holds only a few point-in-time snapshots. This sprint handles that on two
tracks, and the engine uses whichever evidence it has:

- **Track A — provider growth windows (works today).** Providers already report
  multi-window figures in a single snapshot: fees/revenue over 24h/7d/30d and price
  change over 24h/7d/30d. From these we derive an *acceleration* signal
  (e.g. 7d run-rate vs 30d run-rate) and compare it to price change — a real,
  information-at-the-time divergence proxy that needs no accumulated history.
- **Track B — cross-time from the append-only history (improves over time).** When
  two observations of a metric exist far enough apart, compute the trend directly
  (value now vs value ~N days ago via `observed_at`). This is the backtestable,
  hindsight-free measure (§10); it engages automatically as history accumulates and
  is preferred over Track A when available.

**Data quality is explicit.** Every signal carries how it was derived and a
`data_quality` figure (completeness, freshness, history depth). Thin data yields an
`insufficient_history`/low-quality signal — never a confident number from nothing
(§10, ADR-003).

## Scope

- **Divergence module** (`src/alphadex/divergence/`)
  - `trends.py` — pure functions computing a **fundamentals trend** (fees/revenue
    acceleration via Track A; fees/revenue/TVL change via Track B) and a
    **price/valuation trend** (price change; a coarse valuation multiple such as
    market-cap-to-annualized-fees and its change), each returning the value **and**
    how it was derived. Missing inputs produce an explicit "unavailable", not `0`.
  - `engine.py` — combine the trends into a **divergence score** (configurable,
    normalized gap between fundamentals improvement and price recognition),
    classify the signal, and assemble the evidence (what changed / why now / what
    supports / what contradicts / what invalidates / major risk).
  - `service.py` — `DivergenceService`: select the assets to analyze (the latest
    scan's candidates + watches by default; configurable to all), load their
    observations, run the engine, and persist a `divergence_run` with per-asset
    `divergence_signals`. Per-asset failure isolation and a run record (reuse the
    Sprint 02–04 pattern).
  - `repository.py` — load the observation history the engine needs; read the
    latest run's ranked signals.
- **Persistence** (migration `0004`, additive/reversible)
  - `divergence_runs` — timestamp, status, config snapshot, counts.
  - `divergence_signals` — `run_id`, `asset_id`, `classification`
    (`fundamental_divergence` / `watch` / `thesis_weakening` / `insufficient_data`),
    `divergence_score` (nullable), `fundamentals_trend`, `price_trend`,
    `valuation_trend`, `window`, `method` (`growth_window` / `cross_time`),
    `data_quality`, `rank`, and an `evidence` JSON (the §10 questions answered).
    Typed decision fields; JSON only for the human-readable evidence.
- **Read API** — `GET /divergences` (latest run's ranked signals; filter by
  classification), `GET /divergences/{asset_id}` (one asset's latest signal with
  full evidence; `404` if not analyzed), `GET /divergence-runs`.
- **Command** — `scripts/run_divergence.py` (one-shot).
- **Config** — divergence windows, thresholds, score weights, minimum history/
  freshness for Track B, and the analysis scope (candidates vs all). All in config,
  validated; never hard-coded (§2, §10).
- **Tests** — trends (Track A and Track B, incl. explicit missing/insufficient
  data), engine (scoring, classification, evidence content, no-inflation on missing
  inputs), service (selection, persistence, isolation, run record), API (evidence,
  filter, `404`, **no blind BUY language**), config validation. Keep all prior
  suites + the foundation gate green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (divergence entities + method),
  `docs/api/` (`/divergences`).

## Out of scope

- The **Valuation Engine** (full, multi-method valuation) and the **Risk Engine**
  (Sprints 06–07). This sprint uses only a *coarse* valuation multiple as one input
  to divergence, clearly labeled — not a valuation verdict.
- The **Alpha Score / Risk Score / Confidence** trio (Sprint 07). The Divergence
  Engine emits a divergence score + data-quality only; it is one component the
  Alpha Score will later combine.
- Tokenomics, technical setup, reporting, notifications, dashboard.
- A **background scheduler** to automate ingestion cadence (Sprint 12). This sprint
  reads whatever history exists and degrades gracefully; building history is done by
  running the existing ingestion commands repeatedly (documented).
- Token value-capture modeling beyond the coarse multiple (does protocol strength
  reach the token) — deeper treatment comes with Tokenomics (Sprint 06).

## Architecture impact

Adds the **Divergence Engine** module (§2) — a pure analytical layer over the
internal data model, following the Scanner's established pattern (config-driven,
explainable, persisted with evidence). It consumes `market.*` and `fundamental.*`
observations and the Scanner's candidate set; it depends on no provider and no
scoring engine. Modular monolith preserved (ADR-001).

## Data impact

- **New (migration `0004`, additive):** `divergence_runs` and `divergence_signals`
  (see Scope). `divergence_score` is nullable and, when absent, carries a
  classification explaining why (e.g. `insufficient_data`) — never a `0` standing in
  for "unknown" (ADR-003). The config used is snapshotted for reproducibility.
- **Reused unchanged:** `assets`, `metric_observations` (read as history — ADR-004),
  `scan_runs`/`scan_results` (candidate selection). Divergence signals are **derived
  data**, regenerable by re-running the engine.
- **No hindsight bias (§10):** Track B compares observations by their `observed_at`;
  the engine never uses information newer than the point it is reasoning about.

## API impact

- `GET /divergences` — latest run's signals, ranked by divergence score, filterable
  by classification. Each item exposes the trends, the method used, the
  divergence score, `data_quality`, and the full evidence (what changed / why now /
  supports / contradicts / invalidates / major risk). Language is constrained to
  *fundamental divergence, watch, thesis weakening, risk elevated* — **never** BUY/
  GUARANTEED (§10).
- `GET /divergences/{asset_id}` — one asset's latest signal; `404` if not analyzed.
- `GET /divergence-runs` — recent runs with counts. Prior endpoints unchanged.

## UI impact

None (dashboard deferred to Sprint 10). `/divergences` is the richest human-readable
JSON surface yet — the first that answers "why is this interesting?".

## Implementation tasks

1. `divergence/trends.py` — fundamentals + price/valuation trends (Track A & B),
   each with derivation metadata and explicit missing/insufficient handling.
2. `divergence/engine.py` — divergence score, classification, evidence assembly.
3. Migration `0004` — `divergence_runs`, `divergence_signals`; verify up/down.
4. `divergence/service.py` — candidate selection, run engine, persist, isolate.
5. `divergence/repository.py` + `api/routes/divergences.py` (+ runs); register.
6. `scripts/run_divergence.py` — one-shot entrypoint.
7. `config.py` + `.env.example` — windows, thresholds, weights, min-history, scope.
8. Tests (trends, engine, service, API, config); keep prior suites + foundation
   gate green.
9. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
10. Verify end-to-end on Docker + PostgreSQL: ingest market + fundamentals (twice,
    to seed a little Track-B history), run a scan, run divergence, and confirm
    `/divergences` returns explainable, ranked signals with data-quality honest
    about thin history.

## Testing strategy

- **Unit — trends:** Track A acceleration from fees_7d/30d and price windows
  matches hand-computed values; Track B trend from two seeded observations at known
  `observed_at` is correct and is preferred when present; a missing/again-single
  observation yields `insufficient_history`, not a fabricated trend or `0`.
- **Unit — engine:** the divergence score is a deterministic function of the trends
  and configured weights; a strong-fundamentals/lagging-price asset scores high and
  classifies `fundamental_divergence`; fundamentals down or price-ran-ahead
  classifies `thesis_weakening`; missing inputs never inflate the score; the evidence
  answers each §10 question and contains no BUY language.
- **Integration — service (SQLite):** seeded observations + a scan produce a
  `divergence_run` with `divergence_signals` for the selected assets; a per-asset
  failure is isolated; scope config (candidates vs all) is honored; re-running keeps
  history.
- **API:** `/divergences` returns ranked, explainable signals; classification filter
  works; `/divergences/{id}` `404` when not analyzed; a scan-free/empty DB returns
  `[]`; a scan of the serialized output asserts no forbidden BUY terms appear.
- **Config:** score weights validated; invalid config rejected clearly.
- Deterministic; SQLite for portable runs, PostgreSQL via Docker. Foundation gate
  stays green.

## Acceptance criteria

- `uv run pytest` passes (new + prior suites); the foundation gate still passes.
- `alembic upgrade head` applies `0004` (and `downgrade` reverses it).
- Divergence signals are computed and persisted with the trends, the method used,
  a divergence score (or an explicit `insufficient_data` classification with a
  `null` score — never `0`), full §10 evidence, and a `data_quality` figure.
- Track A works with a single snapshot; Track B is used and preferred when history
  exists; thin data is surfaced honestly (§10).
- `GET /divergences` returns ranked, explainable signals; **no BUY/GUARANTEED
  language** anywhere.
- The engine depends only on the internal data model. `ruff` clean, `mypy` clean;
  no out-of-scope engines (valuation/risk/alpha) introduced.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` updated; Sprint 05 report
  completed.
- Release gate (AGENTS.md §7): tests pass → Docker builds → app starts →
  migrations apply → ingest + scan + divergence + read workflow works → docs updated
  → release commit → tag `v0.5.0` at the release head.

## Risks

- **Thin history makes Track B weak initially.** Mitigation: Track A gives an
  immediate, honest signal from provider growth windows; `data_quality` states the
  limitation; the engine improves automatically as history accrues.
- **Divergence ≠ opportunity (over-claiming).** Mitigation: strict §10 language,
  explicit `what_contradicts`/`what_invalidates`/`major_risk` on every signal, and
  keeping this a *component*, not a verdict (no Alpha Score here).
- **Valuation-multiple naivety.** Mitigation: the multiple is a coarse divergence
  input, explicitly labeled; real valuation is Sprint 06–07.
- **Hindsight bias.** Mitigation: Track B keys strictly off `observed_at`; tests
  assert no use of future information.
- **Scope creep into valuation/risk/scoring.** Mitigation: the Out-of-scope list;
  the engine emits divergence + data-quality only.

## Rollback considerations

Migration `0004` is additive with a working `downgrade()`: `alembic downgrade -1`
drops `divergence_runs` and `divergence_signals` (Sprints 01–04 schema untouched).
Divergence signals are **derived data**, regenerable by re-running the engine, so
dropping them loses no source information. The engine is read-only over existing
observations/scan results, so ingestion, scan, and read paths are unaffected.
`git checkout v0.4.0` returns to the Scanner foundation; `v0.4.0` remains the prior
stable anchor and `v0.5.0` becomes the next once tagged.
