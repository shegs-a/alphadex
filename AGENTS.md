# AGENTS.md — AlphaDex Scout Engineering Rules

> Persistent engineering rules for AlphaDex Scout, a Crypto Alpha Intelligence
> System by Ciphercrib Solutions. Read this file **first** at the start of every
> task. Update it only when a **durable** engineering rule changes — this is not a
> changelog.

---

## 1. Mission

AlphaDex Scout identifies potentially **mispriced** crypto assets by finding
**evidence-backed divergence** between improving economic fundamentals and lagging
market price/valuation.

Core thesis: *"Find crypto assets where underlying economic activity and
fundamentals are improving materially faster than market price/valuation is
recognizing."*

The system is **not** a pump predictor and **not** a generic dashboard. It must
distinguish, and never conflate:

1. A protocol becoming economically stronger.
2. A token benefiting from that strength.
3. A token being attractively valued.
4. A technically actionable entry existing.

Every feature must advance: **Discovery → Evidence → Divergence → Valuation →
Risk → Setup → Decision.** Challenge any requirement that does not.

---

## 2. Architecture Principles

- **Modular monolith first.** One deployable application with strong internal
  module boundaries. No microservices, Kubernetes, Kafka, service mesh, or event
  buses until a concrete requirement justifies them (see `docs/decisions/ADR-001`).
- **Provider abstraction.** Business logic depends on interfaces
  (`MarketDataProvider`, `FundamentalDataProvider`, `TokenomicsProvider`,
  `HistoricalDataProvider`), never on a concrete external API.
- **Separate raw from normalized.** Provider Data → Validation → Normalization →
  Internal Data Model. Never let a provider's shape leak into the scoring engine.
- **Historical, append-only observations.** Store observations
  (`asset, metric, value, period, observed_at, source`), not just current values,
  so the system is backtestable (see `docs/decisions/ADR-004`).
- **Explainability over black-box scores.** Every score exposes its components and
  the evidence behind them.
- **Configurable, not hard-coded.** Scoring weights, thresholds, and the asset
  universe live in configuration, never scattered through the code.

Target module boundaries (internal, not separate services):
Market Data · Fundamental Data · Tokenomics · Normalization · Opportunity Scanner ·
Divergence Engine · Valuation Engine · Risk Engine · Scoring Engine · Technical
Analysis · Reporting · Notifications · API · Dashboard.

---

## 3. Technology Stack

Decided in `docs/decisions/ADR-002`. Summary:

| Concern            | Choice                                    |
|--------------------|-------------------------------------------|
| Language           | Python 3.11+ (3.12 in Docker image)       |
| API framework      | FastAPI + Uvicorn                         |
| Database           | PostgreSQL 16                             |
| ORM                | SQLAlchemy 2.0                            |
| Migrations         | Alembic                                   |
| Config             | pydantic-settings (env-driven)           |
| HTTP client        | httpx                                     |
| Scheduling         | APScheduler (in-process, initially)       |
| Logging            | structlog (structured)                    |
| Testing            | pytest, pytest-asyncio, httpx test client |
| Lint / format      | ruff                                      |
| Type checking      | mypy                                      |
| Packaging / env    | uv + `pyproject.toml`                      |
| Containerization   | Docker + Docker Compose                   |

Do not add a frontend framework until a real UI requirement exists (Sprint 10).

---

## 4. Repository Structure

```
/
├── AGENTS.md            # this file — persistent engineering rules
├── README.md            # onboarding + how to run
├── CHANGELOG.md         # per-release notes (semantic versioning)
├── .env.example         # documented config; never real secrets
├── .gitignore
├── docker-compose.yml   # (added in Sprint 01)
├── pyproject.toml       # (added in Sprint 01)
├── docs/
│   ├── architecture/    # system overview + diagrams
│   ├── decisions/       # ADRs (architecture decision records)
│   ├── data/            # data model, metric definitions, provenance
│   ├── api/             # API contracts
│   └── sprints/         # sprint-NN-plan.md + sprint-NN-report.md
├── src/alphadex/        # application code (added in Sprint 01)
├── tests/               # unit / integration / regression / data-quality
├── migrations/          # Alembic migrations (added in Sprint 01)
└── scripts/             # operational + dev scripts
```

---

## 5. Development Commands

```bash
uv sync --extra dev         # install/lock dependencies (incl. dev tools)
uv run ruff check .         # lint
uv run ruff format .        # format
uv run mypy src             # type check
uv run pytest               # full test suite (also runs the foundation gate)
uv run alembic upgrade head # apply migrations
uv run uvicorn alphadex.api.app:app --reload   # run API locally
```

The dependency-free foundation gate (stdlib only, no deps required) is run as a
targeted module — do not use `unittest discover`, which now collides with the
pytest-style suite:

```bash
python3 -m unittest tests.test_foundation -v
```

---

## 6. Docker Commands (Sprint 01+)

```bash
docker compose up --build   # full local dev environment
docker compose down         # stop
docker compose exec app alembic upgrade head   # migrate inside container
```

Docker rules: configure via environment variables, never hard-code secrets,
persist the database volume, define health checks, declare sensible
`depends_on`, keep builds reproducible, and do not add containers for fashion.
The same architecture must run on a developer laptop and a single cloud VM with
minimal differences.

---

## 7. Git, Versioning & Release Rules

- Semantic versioning `MAJOR.MINOR.PATCH`. Every stable release is a Git tag
  pointing to a specific commit (`git tag -a v0.1.0 -m "..."`).
- Stable releases live on `main`; use `feature/...` and `fix/...` branches.
- Meaningful commits (`feat:`, `fix:`, `test:`, `refactor:`, `docs:`). Never
  `changes`, `stuff`, `final2`.
- **Rollback is mandatory.** Never rewrite history that contains stable releases;
  never squash/delete historical tags to tidy the log. The Git history is part of
  the engineering system.
- Release discipline before tagging: tests pass → Docker builds → app starts →
  migrations apply → primary workflow works → diff reviewed → docs + CHANGELOG
  updated → release commit → tag → recorded in the sprint report.

---

## 8. Coding Conventions

- Type hints everywhere; `mypy` clean.
- `ruff` for lint + format; no manual style debates.
- Small, single-responsibility modules aligned to the boundaries in §2.
- Structured logging via `structlog`: log what happened, when, which asset, which
  provider, success/failure and why. Never log secrets. Avoid noisy logs.
- Errors are observable, never silently swallowed. One asset's provider failure
  must not crash the pipeline — record it and continue where safe.
- Parameterized queries / ORM only. Never expose internal stack traces to API
  consumers.

---

## 9. Data Rules

- **Missing data is explicit**, never `0`. Use `UNKNOWN`, `NOT_AVAILABLE`,
  `NOT_APPLICABLE` (see `docs/decisions/ADR-003`).
- Preserve metric distinctions: **Fees ≠ Revenue ≠ Holders Revenue ≠ Price
  Appreciation.** Never treat them as interchangeable.
- Preserve provenance for important metrics: provider, timestamp, metric, asset,
  period, source status, freshness.
- Core analytical data uses structured schemas + migrations; JSON/JSONB only for
  genuinely flexible provider-specific metadata. Never manually mutate schemas.
- Tiered processing to control cost: cheap screening on the broad universe →
  deeper analysis on candidates → richest analysis on high-conviction setups. Do
  not fetch expensive data for assets that fail the initial screen.

---

## 10. Scoring & Output Rules

- **Alpha Score, Risk Score, and Confidence are three separate outputs.** A high
  Alpha Score with unacceptable risk or low confidence is not a top candidate.
- Alpha Score weights are configurable (default: Economic Growth 25, Divergence
  20, Valuation 15, Token Value Capture 15, Market Strength 10, Tokenomics 10,
  Technical Setup 5) and stored in config, not hard-coded.
- Every signal answers: why interesting, why now, what changed, what supports it,
  what contradicts it, what invalidates it, what is the major risk.
- **No blind BUY signals.** Never emit `BUY NOW`, `GUARANTEED`, `100% PUMP`, `RISK
  FREE`. Use: *potential opportunity, watch, high-interest candidate, fundamental
  divergence, technical setup forming, risk elevated, thesis weakening.*
- Confidence depends on data completeness, freshness, signal agreement, and
  strength of divergence. Poor-quality data must not yield high confidence.
- Never optimize the scoring model against today's winners (no hindsight bias);
  signals must use information available at the time.

---

## 11. Testing Rules

- Every significant module has tests: unit (calculations, scoring, normalization,
  valuation, risk, divergence), integration (db, providers, API, pipeline),
  regression, and data-quality.
- Deterministic tests. Do not depend on live external APIs — use fixtures/mocks.
- Never delete or disable a test to make a sprint pass. If a test fails, fix the
  code or document the failure — do not hide it.

---

## 12. Security Rules

- Never commit secrets (API keys, DB passwords, Telegram/exchange tokens, cloud
  creds, env-specific URLs). Use env config; keep `.env.example` documented.
- Validate all external input. Parameterized queries only.
- Do not leak stack traces to API consumers. Do not log credentials.
- Keep dependencies reasonably current and vetted before adding (see §14).

---

## 13. Data Provider Rules

- Every integration handles: missing/stale data, API failures, rate limits,
  malformed responses, inconsistent units, duplicate assets, symbol collisions,
  chain differences, outages.
- Providers sit behind interfaces so they can be swapped without touching the
  scoring engine.
- Do not treat missing provider data as zero.

---

## 14. Dependency Discipline

Before adding a dependency ask: do we need it, is it already available, is it
mature and maintained, does it materially reduce complexity, what are the
security/licensing implications, does it add operational complexity? Do not add
libraries because they are fashionable.

---

## 15. Sprint Rules

- Roadmap: Sprint 00 Foundation → 01 Platform → 02 Market Data → 03 Fundamentals →
  04 Scanner → 05 Divergence → 06 Tokenomics & Risk → 07 Alpha Scoring → 08
  Technical → 09 Reporting & Notifications → 10 Dashboard → 11 Historical &
  Backtesting → 12 Hardening & Deployment. Split a sprint if it grows too large.
- Every sprint has `docs/sprints/sprint-NN-plan.md` and `-report.md`.
- Execution: read AGENTS.md → read the sprint plan → inspect existing code →
  propose a short plan → implement only approved scope → test → review diff →
  update the report → prepare the release.
- A sprint is complete only when the completion checklist (README §
  "Sprint Completion") passes. Code written ≠ sprint done. Never claim something
  was completed if it was not implemented **and** tested.

---

## 16. AI-Agent Cost Controls

- Read AGENTS.md and the relevant sprint plan; inspect only the relevant code.
- Determine the smallest set of files needed; implement; run targeted tests, then
  broader regression tests when appropriate; update docs.
- Do not reread the whole repository unnecessarily. Do not redesign the system for
  a small feature. Keep tasks bounded.

---

## 17. No Destructive Autonomy

Do not delete large parts of the project, replace architecture wholesale, rewrite
working modules needlessly, change schemas destructively without migration, remove
tests or error handling, or add dependencies without evaluation.

If a major architectural change seems necessary and is outside the current sprint
scope, **STOP** and present: current architecture, problem, proposed change,
alternatives, trade-offs, migration impact, rollback strategy — then wait for
approval.

---

## 18. Priority Order When Uncertain

1. Correctness → 2. Data integrity → 3. Security → 4. Explainability →
5. Testability → 6. Maintainability → 7. Reversibility → 8. Operational
simplicity → 9. Performance → 10. Convenience.

Never sacrifice correctness or data integrity to move faster. Do not overengineer
in the name of quality. Goal: *simple architecture, strong boundaries, excellent
testing, clear documentation, reproducible deployment, reversible releases.*
