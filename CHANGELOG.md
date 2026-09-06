# Changelog

All notable changes to AlphaDex Scout are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_Work toward the next release. Move entries under a version heading on release._

## [0.0.0] — 2026-09-06

### Added
- Engineering foundation for AlphaDex Scout (Sprint 00):
  - `AGENTS.md` — persistent engineering rules (mission, architecture, stack,
    Git/release, data, scoring, testing, security rules, cost controls).
  - `README.md` — product overview, architecture, setup, workflow.
  - Documentation structure: `docs/architecture/`, `docs/decisions/`,
    `docs/data/`, `docs/api/`, `docs/sprints/`.
  - Architecture Decision Records ADR-001 (modular monolith), ADR-002
    (technology stack), ADR-003 (missing-data representation), ADR-004
    (historical observations model).
  - Sprint process: plan/report templates, `sprint-00-plan.md`,
    `sprint-00-report.md`.
  - `.env.example` and `.gitignore`.
  - Dependency-free foundation test gate (`tests/`, stdlib `unittest`).

### Notes
- `0.0.0` marks the engineering foundation only. No application, database, Docker
  environment, or providers yet — those begin in Sprint 01 (Platform Foundation),
  targeting `v0.1.0`.
