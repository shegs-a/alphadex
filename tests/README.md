# Tests

- **Sprint 00 (now):** a dependency-free foundation gate (`test_foundation.py`)
  written with the stdlib `unittest` runner — it verifies the repository's
  engineering foundation is present and consistent, and runs before the Python
  dependency stack exists.

  ```bash
  python3 -m unittest discover -s tests -v
  ```

- **Sprint 01+:** the full suite runs under `pytest` (unit, integration,
  regression, data-quality). `unittest.TestCase` tests are also collected by
  pytest, so the foundation gate continues to run.

  ```bash
  uv run pytest
  ```

Tests are deterministic and never depend on live external APIs; providers are
mocked with fixtures.
