# Sprints

Every sprint has two documents:

- `sprint-NN-plan.md` — written **before** implementation.
- `sprint-NN-report.md` — completed **at the end** of the sprint.

`NN` is the zero-padded sprint number (`00`, `01`, …). Templates below.

## Roadmap

| Sprint | Theme |
|---|---|
| 00 | Architecture & Engineering Foundation |
| 01 | Platform Foundation (app skeleton, DB, Docker, `/health`) |
| 02 | Market Data Foundation |
| 03 | Fundamental Intelligence |
| 04 | Opportunity Scanner |
| 05 | Economic Divergence Engine |
| 06 | Tokenomics & Risk Engine |
| 07 | Alpha Scoring Engine |
| 08 | Valuation Engine |
| 09 | Reporting & Notifications |
| 10 | Dashboard |
| 11 | Historical Intelligence & Backtesting |
| 12 | Hardening & Production Deployment |
| — | Technical Setup Engine (reordered after Sprint 08; unscheduled) |

Sprint 08 was reordered from Technical Setup to the **Valuation Engine** — the larger
lever on Alpha Confidence (weight 15 vs 5). Technical Setup (the remaining
`not_implemented` Alpha component) is deferred to a later, currently unscheduled sprint.

Split a sprint if it grows too large.

---

## Plan template

```markdown
# Sprint NN Plan — <Title>

- Objective
- Problem being solved
- Scope
- Out of scope
- Architecture impact
- Data impact
- API impact
- UI impact
- Implementation tasks
- Testing strategy
- Acceptance criteria
- Exit criteria
- Risks
- Rollback considerations
```

## Report template

```markdown
# Sprint NN Report — <Title>

- Sprint objective
- Completed tasks
- Incomplete tasks
- Files/modules changed
- Database changes
- API changes
- Configuration changes
- Tests executed
- Test results
- Bugs discovered / fixed
- Known limitations
- Technical debt
- Deviations from the plan
- Architecture decisions
- Release/version created (Git commit/tag)
- Rollback procedure
- Recommended next steps
```
