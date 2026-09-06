# Tests

- **Full suite (canonical):** runs under `pytest` — unit, data-quality, migration,
  and the foundation gate (pytest also collects `unittest.TestCase` tests).

  ```bash
  uv run pytest
  ```

- **Dependency-free foundation gate:** `test_foundation.py` uses the stdlib
  `unittest` runner and needs no third-party packages. Invoke it as a **targeted
  module** (not `unittest discover`, which would try to import the pytest-style
  modules that require the installed dependencies):

  ```bash
  python3 -m unittest tests.test_foundation -v
  ```

Layout: `test_foundation.py` (structure/invariants), `test_config.py`,
`test_health.py`, `test_models_data_quality.py` (ADR-003/004), `test_migration.py`
(Alembic smoke). `conftest.py` provides an in-memory SQLite engine/session.

Tests are deterministic and never depend on live external APIs; providers are
mocked with fixtures.
