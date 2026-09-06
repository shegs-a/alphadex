# Sprint 00 Plan — Architecture & Engineering Foundation

## Objective

Establish the engineering foundation for AlphaDex Scout: the persistent rules,
documentation structure, architecture decisions, sprint process, and a runnable
test gate — so that all subsequent sprints have a disciplined, reversible,
well-documented base to build on. **No application code is built in this sprint.**

## Problem being solved

Building a data-intensive intelligence system without an agreed architecture,
technology stack, data-integrity contract, and sprint/release discipline leads to
inconsistent decisions, hidden data corruption (e.g. missing data treated as `0`),
un-backtestable history, and irreversible releases. Sprint 00 removes that risk up
front and records the reasoning so future contributors (human or AI) do not
re-derive it.

## Scope

- `AGENTS.md` — persistent engineering rules.
- `README.md` — product overview, architecture, setup, workflow, current status.
- `CHANGELOG.md` — initialized (Keep a Changelog + SemVer).
- `.gitignore`, `.env.example` (documented, no secrets).
- Documentation tree: `docs/architecture/`, `docs/decisions/`, `docs/data/`,
  `docs/api/`, `docs/sprints/`.
- `docs/architecture/overview.md` — intended architecture + diagrams.
- ADRs: 001 modular monolith, 002 technology stack, 003 missing-data
  representation, 004 historical observations model.
- Sprint process (`docs/sprints/README.md` with templates) + this plan + the
  Sprint 00 report.
- `tests/` with a dependency-free foundation test gate (stdlib `unittest`).

## Out of scope

- Any application/source code (`src/alphadex/`), the API, or the `/health` endpoint.
- `docker-compose.yml`, `pyproject.toml`, Alembic/migrations, the database.
- Any data provider integration, scoring, divergence, valuation, or risk logic.
- Installing the Python dependency stack (pytest, FastAPI, etc.).

All of the above belong to Sprint 01+ and are intentionally deferred.

## Architecture impact

Defines the target architecture (modular monolith) and module boundaries but adds
no runtime components. Establishes the constraints all future sprints inherit.

## Data impact

None at runtime. Establishes the binding data contracts (ADR-003 missing-data,
ADR-004 historical observations) that Sprint 01/02 schemas must implement.

## API impact

None. Documents the planned resource surface only (`docs/api/README.md`).

## UI impact

None. Dashboard deferred to Sprint 10.

## Implementation tasks

1. Write `AGENTS.md`.
2. Write `README.md`, `CHANGELOG.md`, `.gitignore`, `.env.example`.
3. Create the `docs/` tree and `docs/architecture/overview.md`.
4. Write ADR-001..004.
5. Write the sprint process README + templates.
6. Write this plan and the Sprint 00 report.
7. Add the `tests/` foundation gate (verifies required foundation files exist).
8. Run the test gate; confirm green.
9. Review the diff; commit; tag `v0.0.0`; push the branch.

## Testing strategy

Sprint 00 has no application logic to unit-test. The appropriate gate is a
**foundation/structure test**: a stdlib `unittest` suite asserting that every
required foundation artifact exists (AGENTS.md, README, CHANGELOG, the ADRs, this
plan, the report, `.env.example`, `.gitignore`, the docs tree). Dependency-free so
it runs before the Python stack exists. The full pytest-based unit/integration/
regression/data-quality suites begin in Sprint 01.

## Acceptance criteria

- All in-scope files exist and are internally consistent.
- ADR-003 and ADR-004 clearly bind future schema work.
- `python3 -m unittest discover -s tests -v` passes with zero failures.
- No application code, Docker, or DB artifacts were introduced.

## Exit criteria

- Acceptance criteria met.
- Diff reviewed; a stable commit created on `claude/resume-session-devices-ibdww4`.
- Release `v0.0.0` tagged at that commit.
- Sprint 00 report completed and committed.
- Branch pushed.

## Risks

- **Over-scoping** into Sprint 01 (building the app now). Mitigation: strict scope
  boundary above.
- **Stack decision churn.** Mitigation: decisions recorded as ADRs with
  alternatives; changeable via a superseding ADR without rework.
- **Docs drifting from reality** later. Mitigation: AGENTS.md is rules-only;
  per-sprint reality lives in sprint reports and CHANGELOG.

## Rollback considerations

This sprint adds only documentation, config templates, and a test — no runtime,
schema, or destructive change. Rollback is trivial: `git checkout` the previous
commit, or simply do not tag `v0.0.0`. Because it is the first commit, there is no
prior state to protect; the tag `v0.0.0` becomes the first rollback anchor for
Sprint 01.
