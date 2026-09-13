# Sprint 08 Plan — Valuation Engine

## Objective

Build the **Valuation Engine** — the component that answers "is this asset cheap or
expensive **relative to the economics it generates**?" — and wire it into the Alpha
Score as the first component to graduate from `not_implemented`. It produces a
normalized **valuation attractiveness** in [0,1] (higher = cheaper) per asset from a
set of distinct valuation multiples, persists it with evidence, and feeds the Alpha
`valuation` component (weight 15). This is the biggest lever on the current
`low_confidence` problem: for assets with valuation data, `model_completeness` rises
from 0.80 to 0.95 — validating the ADR-006 promise that a component slots in with **no
scoring rewrite**.

## Problem being solved

AlphaDex's thesis is fundamentals improving faster than the market **prices them**
(§1). Divergence measures the *trend* gap; Valuation measures the *level* — a protocol
can have improving fundamentals yet already trade at a rich multiple (expensive), or
lagging attention yet trade cheap (attractive). Until now the Valuation Alpha component
was `not_implemented` (weight 15 renormalized out, capping Confidence at 0.80). This
sprint makes it real, so "cheap relative to fundamentals" becomes a first-class,
explainable input — and 72/90 assets stuck at `low_confidence` gain a path to higher
completeness.

## Guardrails (approved constraints)

Binding for this sprint (hard acceptance criteria, verified by tests and wording):

1. **Attractiveness is not a fair-value claim.** The output is *relative cheapness vs
   the economics the asset generates*, never an assertion of intrinsic/fair value.
   Field names (`valuation_score` / attractiveness), labels
   (`cheap`/`fair`/`expensive` — a relative reading, not "undervalued"/"correctly
   priced"), evidence text, and docstrings all say so. No BUY/GUARANTEED (§10).
2. **Reference multiples are heuristic baselines, not universal fair values.** Each
   `ref_*` marks "around here reads as mid-range for this metric" — documented as a
   configurable heuristic, explicitly not a market truth, in config, `docs/data`, and
   the evidence.
3. **Completeness stays separate from attractiveness.** `data_completeness` is its own
   field; it never scales, discounts, or is blended into `valuation_score` (ADR-005
   discipline). Thin data raises uncertainty downstream (Alpha Confidence), never a
   fake cheap/expensive reading.
4. **Mixed/conflicting and single-multiple evidence is tested.** Explicit cases: an
   asset cheap on one multiple but expensive on another (the blend lands between and
   the evidence surfaces both sides), and an asset with exactly one measurable multiple
   (scored on that alone, low completeness, not fabricated).
5. **The four multiples retain distinct economic meanings.** MC/fees (gross economic
   throughput), MC/revenue (protocol take), MC/holders-revenue (accrual to holders),
   MC/TVL (capital efficiency) are computed from distinct inputs, stored in distinct
   columns, and explained on distinct evidence lines — never collapsed or averaged into
   a single "multiple" (§9).
6. **No tuning against known winners.** References and blend weights are documented
   defaults, deliberately not fitted to any known outcome (§10, no hindsight bias);
   tuning is a backtesting concern (Sprint 11).
7. **No redesign of Alpha, Risk, or Confidence.** The `valuation` component graduates
   from `not_implemented` to consuming `valuation_score`; the Alpha formula, ranking,
   the three-output contract, and Risk/Confidence are untouched (ADR-006 upheld).
8. **No Technical Setup this sprint.** Its Alpha component stays `not_implemented`;
   completeness caps at 0.95.

## Scope

- **Valuation module** (`src/alphadex/valuation/`)
  - `multiples.py` — pure functions, each a valuation **multiple or `None`** when
    inputs are missing (explicit missing-data, never `0` — ADR-003; a zero denominator
    → `None`, never a false `0`):
    - `price_to_fees` = market cap / annualized fees_30d,
    - `price_to_revenue` = market cap / annualized revenue_30d,
    - `price_to_holders_revenue` = market cap / annualized holders_revenue_30d,
    - `mcap_to_tvl` = market cap / TVL.
    Fees ≠ Revenue ≠ Holders Revenue kept distinct (§9). Market cap (circulating) is
    the numerator; dilution is a **separate** concern already owned by Tokenomics.
  - `score.py` — normalize each multiple to an **attractiveness** in [0,1] against a
    configured reference (lower multiple = cheaper = more attractive; a smooth,
    bounded, monotonic mapping `ref / (ref + multiple)` → 0.5 at the reference), blend
    the **available** ones with renormalized weights into a `valuation_score`
    (`None` unless at least one multiple is measurable — dilution-style discipline),
    a `valuation_label` (`cheap`/`fair`/`expensive`/`unknown`), a separate
    `data_completeness`, and evidence. Raw multiples are always exposed alongside.
  - `service.py` + `repository.py` — run over the Scanner's candidates using the
    shared `alphadex.analysis` base; per-asset SAVEPOINT isolation; a run record;
    rank by valuation attractiveness (a component ranking, not an opportunity ranking).
  - `config.py` — scope, references, blend weights (sum to 1.0), band cut points;
    validated. Documented heuristics, never hard-coded (§2); not fitted to outcomes
    (§10).
- **Alpha integration** — the `valuation` component adapter stops returning
  `not_implemented` and instead consumes the latest `valuation_score` (available when
  measured, unavailable when `None` — exactly like `token_value_capture`). The Alpha
  service loads the latest valuation assessment per asset and passes it in. **No change
  to the Alpha Score formula, ranking, or the three-output contract** — completeness
  simply rises. `technical_setup` remains `not_implemented`.
- **Persistence** (migration `0008`, additive/reversible) — `valuation_runs` and
  `valuation_assessments`: `valuation_score` (nullable) + `valuation_label`, the four
  distinct multiples, `data_completeness`, `rank`, `evidence` JSON. Nullable scores are
  `NULL` with a label, never `0`.
- **Read API** — `GET /valuations` (filter by label; ranked by attractiveness),
  `GET /valuations/{asset_id}`, `GET /valuation-runs`.
- **Command** — `scripts/run_valuation.py` (runs before `run_alpha.py` in the pipeline).
- **Docs** — update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`, the
  roadmap (`docs/sprints/README.md`: 08 → Valuation Engine; Technical Setup moves to a
  later slot), and add a dated **note to ADR-006** recording that Valuation is now
  implemented so the renormalization applies to `technical_setup` only.
- **Tests** — multiples (each; missing → `None`; zero denominator → `None`), score
  (normalization direction, renormalized blend, `None` unless measurable, labels),
  service (persist/rank/isolation, SQLite), API (shapes/filter/404/no-BUY), the Alpha
  integration (valuation now available lifts completeness toward 0.95; the no-inflation
  and completeness-tie invariants still hold; `technical_setup` still absent). Keep all
  prior suites + foundation gate green.

## Out of scope

- **Technical Setup engine** (now a later sprint) — its Alpha component stays
  `not_implemented` and is absorbed by Confidence, so completeness caps at 0.95.
- DCF, peer-relative/sector-relative valuation, growth-adjusted multiples (PEG-style),
  or historical multiple percentiles — deliberately deferred; this sprint ships coarse,
  honest, absolute multiples with documented references. Regime/sector awareness is a
  future extension point (no data to justify it yet).
- Reporting/notifications (09), dashboard (10), backtesting and outcome-based weight
  tuning (11), scheduler (12). No new providers.
- Any change to divergence (ADR-005), tokenomics/risk (Sprint 06), or the Alpha
  Score/Confidence/ranking semantics (ADR-006) — consumed as fixed contracts.

## Architecture impact

Adds the **Valuation Engine** module (§2) — a pure analytical layer reading persisted
observations via the shared `alphadex.analysis` base, depending on no provider. Alpha
gains one more real input; the modular monolith (ADR-001) and the three-output model
(ADR-006) are unchanged. Valuation is a **component**, not the Alpha Score.

## Data impact

- **New (migration `0008`, additive):** `valuation_runs`, `valuation_assessments`.
  Multiples and score are distinct fields; missing/undefined are `NULL`, never `0`
  (ADR-003). Config snapshotted per run. Valuation results are **derived data**,
  regenerable by re-running.
- **Reused unchanged:** `metric_observations` (market cap, fees/revenue/holders-revenue
  30d, TVL), `scan_*` (candidate selection), and the divergence/tokenomics/risk/alpha
  tables. Alpha now additionally reads the latest valuation assessment.

## API impact

- `GET /valuations` — per-candidate valuation from the latest run: `valuation_score`
  (nullable) + `valuation_label`, the four distinct multiples, a separate
  `data_completeness`, `rank`, `evidence`. Ranked by attractiveness (a component
  ranking, not an opportunity ranking). No BUY language (§10). Query: `label`, `limit`,
  `offset`. `GET /valuations/{asset_id}` (404 if not assessed); `GET /valuation-runs`.
- `GET /scores` gains the `valuation` component as `available: true` (with a
  contribution) for assets that now have valuation data; shape unchanged. Prior
  endpoints unchanged.

## UI impact

None (dashboard is a later sprint). `/valuations` is read-only.

## Implementation tasks

1. `valuation/multiples.py` — the four multiples (missing/zero-denominator → `None`).
2. `valuation/score.py` — attractiveness normalization + renormalized blend + label +
   evidence.
3. Migration `0008` — `valuation_runs`, `valuation_assessments`; verify up/down.
4. `valuation/service.py` + `valuation/repository.py`; register
   `api/routes/valuations.py`.
5. `scripts/run_valuation.py`.
6. `config.py` + `.env.example` — references, blend weights, band cut points.
7. **Alpha integration** — `alpha/components.valuation` consumes `valuation_score`;
   `alpha/service` + `alpha/repository` load the latest valuation; update the affected
   alpha tests.
8. Tests; docs (README, CHANGELOG, `docs/data`, `docs/api`, roadmap, ADR-006 note);
   keep prior suites + foundation gate green.
9. Verify end-to-end on Docker + PostgreSQL: ingest → scan → divergence → tokenomics →
   risk → **valuation** → alpha; confirm `/valuations` populated and `/scores` shows
   `valuation` available with `model_completeness` up to ~0.95 for assets with data.

## Testing strategy

- **Unit — multiples:** each computes correctly; a missing input or zero/non-positive
  denominator yields `None` (never `0`); Fees/Revenue/Holders-Revenue stay distinct.
- **Unit — score:** lower multiple → higher attractiveness (monotonic); `ref` maps to
  0.5; blend renormalizes over available multiples; `valuation_score` is `None` unless
  at least one multiple is measurable; labels at the configured cut points; a genuine
  cheap/expensive reading is distinct from `unknown`.
- **Integration — service (SQLite):** seeded observations produce a run + ranked
  assessments; per-asset failure isolated; scope honored; re-run keeps history.
- **API:** `/valuations` shapes/filter/404, no-BUY assertion, empty when no run.
- **Alpha integration:** with a valuation run present, the `valuation` component is
  `available` and `model_completeness` rises toward 0.95; the no-inflation invariant and
  the completeness tie-break still hold; with no valuation run, `valuation` stays
  unavailable (back-compatible). `technical_setup` remains `not_implemented`.
- Deterministic; SQLite + Docker/Postgres. Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes; foundation gate passes; `ruff` + `mypy` clean.
- `alembic upgrade head` applies `0008` (and reverses it).
- Valuation multiples are distinct, explainable, and `NULL` when unmeasurable (never
  `0`); `valuation_score` is `None` unless value was actually measured; weights read
  from config (validated), not fitted to outcomes.
- The Alpha `valuation` component is `available` for assets with valuation data, and
  `model_completeness` reaches ~0.95 for them — **with no change to the Alpha formula,
  ranking, or three-output contract** (ADR-006 upheld). `technical_setup` still absent.
- `/valuations` served read-only; no BUY/GUARANTEED anywhere.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` + roadmap + ADR-006 note + Sprint 08
  report updated.
- Release gate (§7): tests → Docker builds → app starts → migrations apply → full
  pipeline (ingest→scan→divergence→tokenomics→risk→valuation→alpha) + reads work → docs
  updated → release commit → tag `v0.8.0`.

## Risks

- **Coarse multiples misread as precise valuation.** Mitigation: they are absolute,
  documented heuristics with configurable references; `data_completeness` and evidence
  are surfaced; ranking is a component ranking, not an opportunity verdict; DCF/peer/
  historical methods are explicitly out of scope.
- **Zero/negative denominators fabricating cheap/expensive readings.** Mitigation: a
  non-positive denominator → `None` (undefined), never a false `0`; `valuation_score`
  is `None` unless a multiple is genuinely measurable (dilution-style discipline).
- **Breaking the Alpha contract when the component graduates.** Mitigation: the adapter
  mirrors `token_value_capture` exactly (score or `None`); the Alpha formula/ranking are
  untouched; the no-inflation and completeness-tie invariants are re-asserted in tests.
- **Reference values are guesses.** Mitigation: documented as heuristics, configurable,
  and deliberately not tuned to known winners (§10); tuning is a backtesting concern
  (Sprint 11).

## Rollback considerations

Migration `0008` is additive with a working `downgrade()`: `alembic downgrade -1` drops
`valuation_runs` / `valuation_assessments` (Sprints 01–07 schema untouched). If the
valuation tables/data are absent, the Alpha `valuation` component simply reports
unavailable again (completeness returns to 0.80) — fully back-compatible. Valuation
results are derived data, regenerable by re-running. `git checkout v0.7.0` returns to
the Alpha Scoring foundation; `v0.7.0` remains the prior stable anchor and `v0.8.0`
becomes the next once tagged.
