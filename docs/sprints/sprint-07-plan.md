# Sprint 07 Plan — Alpha Scoring Engine

## Objective

Combine the components built so far into the system's headline output — but as
**three separate outputs**, never one number (AGENTS.md §10): an **Alpha Score**
(configurable weighted blend of attractiveness components), a **Risk Score** (from
the Sprint 06 Risk engine, surfaced alongside — not folded in), and a **Confidence**
(how much to trust the Alpha Score, given data completeness/freshness/agreement).
Rank opportunities by Alpha Score with Risk and Confidence shown separately, classify
an overall **decision status** in the allowed vocabulary (never BUY), and persist it
all with evidence. This is the culmination of Discovery → Evidence → Divergence →
Valuation → Risk → Setup → **Decision**.

## Problem being solved

Sprints 02–06 produced data and several component signals (divergence, token value
capture, risk, plus market/fundamental observations). Nothing yet answers "all things
considered, how interesting is this asset, how risky, and how much do we trust that?"
The Alpha Scoring Engine assembles the components into a decision-support output —
while rigorously keeping Alpha, Risk, and Confidence separate (a high Alpha with
unacceptable Risk or low Confidence is **not** a top candidate) and refusing blind BUY
language (§10).

## Component availability (read this first)

AGENTS.md §10 defines the default Alpha weight vector (sums to 100):

| Component | Weight | Source this sprint |
|---|---|---|
| Economic Growth | 25 | fundamentals trend (fees/revenue growth) from the divergence inputs |
| Divergence | 20 | divergence **classification/score** (ADR-005) |
| Valuation | 15 | **not implemented** (deferred; a real Valuation engine is future) |
| Token Value Capture | 15 | Sprint 06 `value_capture_score` |
| Market Strength | 10 | market data (momentum + liquidity) |
| Tokenomics | 10 | Sprint 06 `float_ratio` (dilution/float health) |
| Technical Setup | 5 | **not implemented** (Sprint 08) |

Two components (Valuation, Technical Setup — 20% of the intended weight) are not built
yet. **They are handled the same way as any missing input** (ADR-003/ADR-005
discipline): the Alpha Score is computed over the components that are *implemented and
available for the asset*, with weights **renormalized** over what is present, and the
absence is reflected in **Confidence** (a `model_completeness` term), never by
zero-filling. As Valuation and Technical land in later sprints they slot in
automatically and Confidence rises. The full 7-component vector lives in config now so
the target model is explicit and stable.

## Scope

- **Alpha module** (`src/alphadex/alpha/`)
  - `components.py` — pure adapters turning each engine's latest output into a
    normalized **alpha contribution** in [0,1] (higher = more attractive), each
    returning the value **and** whether it was available:
    - economic_growth (fundamentals trend, normalized against a reference),
    - divergence (mapped from the **classification**: `potential_mispricing` /
      `fundamental_divergence` contribute positively; `fundamental_repricing` /
      `momentum` / `thesis_weakening` contribute little/none — the opportunity
      interpretation feeds Alpha, not the raw gap, per ADR-005),
    - token_value_capture (`value_capture_score`; absent when `null`),
    - market_strength (price momentum + liquidity turnover),
    - tokenomics (`float_ratio`).
    Valuation and technical_setup return "not implemented".
  - `score.py` — the **Alpha Score** (weighted, renormalized over available
    components) + a per-component breakdown; the **Confidence** (model completeness,
    data quality, freshness, signal agreement, divergence strength) as a separate
    output + band; and a **decision status** combining Alpha + Risk + Confidence.
  - `service.py` + `repository.py` — run over the Scanner's candidates, pulling each
    asset's latest divergence signal, tokenomics signal, risk assessment, and
    market/fundamental observations; persist a run + per-asset scores.
- **Decision status** (allowed vocabulary only, §10): e.g. `high_interest`,
  `potential_opportunity`, `watch`, `risk_elevated`, `low_confidence`,
  `thesis_weakening`, `insufficient_data`. Never BUY/GUARANTEED. A high Alpha with a
  high Risk band or low Confidence is down-classified (not `high_interest`).
- **Persistence** (migration `0007`, additive/reversible): `alpha_runs` and
  `alpha_scores`. `alpha_scores` keeps the three outputs as **distinct columns** —
  `alpha_score`, `risk_score` (+ `risk_band`), `confidence` (+ `confidence_band`) —
  plus `model_completeness`, `status`, `rank`, a `components` JSON breakdown
  (contribution, weight, available per component), and an `evidence` JSON answering
  the §10 questions. Nullable scores are `NULL` with a status, never `0`.
- **Read API** — `GET /scores` (ranked by Alpha Score, Risk + Confidence shown
  separately; filter by status/band), `GET /scores/{asset_id}`, `GET /score-runs`.
- **Command** — `scripts/run_alpha.py`.
- **Config** — the 7-component Alpha weight vector (AGENTS.md defaults, validated to
  sum to 1.0), confidence parameters, decision-status thresholds, scope. Never
  hard-coded (§2, §10). Weights are the documented defaults — **not fitted to any
  known winners** (§10, no hindsight bias).
- **Tests** — components (each, incl. not-implemented and missing → unavailable),
  score (weights, renormalization, three-outputs-separate, no-inflation), confidence
  (poor data → low; complete → higher), status (risk/confidence down-classification;
  no BUY language), service (persist/rank/isolation), API. Keep all prior suites +
  foundation gate green.
- Update `README.md`, `CHANGELOG.md`, `docs/data/` (alpha entities), `docs/api/`,
  and add **ADR-006** recording the Alpha/Risk/Confidence three-output model and the
  renormalize-and-reflect-in-confidence handling of absent components.

## Out of scope

- A real **Valuation engine** and the **Technical Setup engine** (Sprint 08) — their
  Alpha components stay "not implemented" and are absorbed by Confidence.
- Reporting/notifications (Sprint 09), dashboard (Sprint 10), backtesting (Sprint 11),
  scheduler (Sprint 12). No new providers or on-chain data.
- Any change to the divergence (ADR-005) or Sprint 06 tokenomics/risk semantics —
  those are consumed as fixed contracts.
- Tuning weights against historical outcomes (explicitly forbidden, §10).

## Architecture impact

Adds the **Scoring Engine** module (§2) — a pure analytical layer that reads the other
engines' persisted outputs plus observations, using the shared `alphadex.analysis`
base. It depends on no provider. It is the first module that *combines* components, and
it does so without collapsing the three outputs. Modular monolith preserved (ADR-001).

## Data impact

- **New (migration `0007`, additive):** `alpha_runs`, `alpha_scores` (see Scope).
  Alpha/Risk/Confidence are distinct columns. The risk score is snapshotted from the
  latest risk run at scoring time (recorded, reproducible). Config snapshotted per run.
- **Reused unchanged:** divergence, tokenomics, risk results; `metric_observations`;
  `scan_*` (candidate selection). Alpha scores are **derived data**, regenerable.
- **Missing/absent components** are explicit and flow into Confidence — never `0`
  (ADR-003).

## API impact

- `GET /scores` — the ranked opportunity list. Each item shows the **three separate
  outputs** (Alpha Score, Risk Score + band, Confidence + band), the `status`,
  `model_completeness`, the per-component breakdown, and evidence (why interesting /
  why now / what changed / supports / contradicts / invalidates / major risk).
  Language is constrained (§10). Ranking is by Alpha Score; Risk and Confidence are
  **not** folded into the rank — they are shown so a human weighs them.
- `GET /scores/{asset_id}`, `GET /score-runs`. Prior endpoints unchanged.

## UI impact

None (dashboard deferred to Sprint 10). `/scores` is the first endpoint that reads as
a decision-support surface.

## Implementation tasks

1. `alpha/components.py` — component adapters (available/normalized/evidence).
2. `alpha/score.py` — Alpha Score + Confidence + decision status.
3. Migration `0007` — `alpha_runs`, `alpha_scores`; verify up/down.
4. `alpha/service.py` + `alpha/repository.py`; register `api/routes/scores.py`.
5. `scripts/run_alpha.py`.
6. `config.py` + `.env.example` — weight vector, confidence + status thresholds.
7. ADR-006; tests; keep prior suites + foundation gate green.
8. Update `README.md`, `CHANGELOG.md`, `docs/data/`, `docs/api/`.
9. Verify end-to-end on Docker + PostgreSQL: ingest → scan → divergence → tokenomics
   → risk → alpha; confirm `/scores` shows three separate outputs, that
   `model_completeness` reflects the two unimplemented components, and that a
   high-Alpha/high-Risk or low-Confidence asset is not `high_interest`.

## Testing strategy

- **Unit — components:** each adapter normalizes correctly and reports availability;
  divergence maps by classification (repricing/momentum do not score as strong
  opportunity); valuation/technical report not-implemented; a missing input →
  unavailable (never `0`).
- **Unit — score:** Alpha Score renormalizes over available components (two identical
  assets differing only in an absent component get the same Alpha but different
  Confidence); weights come from config; missing inputs never inflate Alpha.
- **Unit — confidence:** poor/complete data yields low/higher confidence; a scenario
  with only 2 of 7 components caps confidence via `model_completeness`.
- **Unit — status:** high Alpha + high Risk band → `risk_elevated` (not
  `high_interest`); high Alpha + low Confidence → `low_confidence`; no forbidden BUY
  terms appear in any field.
- **Integration — service (SQLite):** seeded component outputs produce an
  `alpha_run` + ranked `alpha_scores` with three distinct outputs; per-asset failure
  isolated; scope honored; re-run keeps history.
- **API:** `/scores` shapes, filters, `404`, no-BUY assertion; empty when no run.
- Deterministic; SQLite + Docker/Postgres. Foundation gate stays green.

## Acceptance criteria

- `uv run pytest` passes; foundation gate passes.
- `alembic upgrade head` applies `0007` (and reverses it).
- **Alpha Score, Risk Score, and Confidence are three separate persisted outputs**
  (distinct columns), each explainable; a missing component is reflected in Confidence,
  never zero-filled into Alpha.
- Alpha weights are read from config (validated), defaulting to the AGENTS.md vector;
  no hindsight-fitted tuning.
- Decision status uses only the allowed vocabulary; high-Risk/low-Confidence assets
  are not surfaced as top opportunities. **No BUY/GUARANTEED** anywhere.
- Engine depends only on internal data. `ruff` clean, `mypy` clean; no out-of-scope
  engines (Valuation/Technical/reporting) built.

## Exit criteria

- Acceptance criteria met; diff reviewed.
- README + CHANGELOG + `docs/data/` + `docs/api/` + ADR-006 + Sprint 07 report updated.
- Release gate (AGENTS.md §7): tests → Docker builds → app starts → migrations apply →
  full pipeline (ingest→scan→divergence→tokenomics→risk→alpha) + reads work → docs
  updated → release commit → tag `v0.7.0`.

## Risks

- **Combining components can hide weak inputs.** Mitigation: three separate outputs;
  Confidence carries data completeness/quality; per-component breakdown persisted;
  no single number.
- **Absent components (Valuation/Technical) distorting Alpha.** Mitigation:
  renormalize over available components and cap Confidence via `model_completeness`;
  documented in ADR-006. Never zero-fill.
- **Divergence contribution double-counting price.** Mitigation: the divergence Alpha
  component is driven by the ADR-005 **classification**, so repricing/momentum do not
  contribute as opportunity; market_strength (momentum) is a separate, small-weight
  component.
- **Hindsight bias in weights.** Mitigation: ship the documented AGENTS.md defaults;
  do not fit to known outcomes; tuning is a backtesting concern (Sprint 11).
- **Scope creep into valuation/technical/reporting.** Mitigation: strict out-of-scope.

## Rollback considerations

Migration `0007` is additive with a working `downgrade()`: `alembic downgrade -1`
drops `alpha_runs` and `alpha_scores` (Sprints 01–06 schema untouched). Alpha scores
are derived data, regenerable by re-running. The engine is read-only over existing
results, so ingestion/scan/divergence/tokenomics/risk and their reads are unaffected.
`git checkout v0.6.1` returns to the Tokenomics/Risk foundation; `v0.6.1` remains the
prior stable anchor and `v0.7.0` becomes the next once tagged.
