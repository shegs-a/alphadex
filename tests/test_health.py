"""Tests for the /health endpoint.

The service must report application and database health separately, and must NOT
report healthy when the database is down (spec §46).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from alphadex import __version__
from alphadex.api.app import app
from alphadex.api.routes import health


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
    # Restore the real probe after each test.
    health.set_db_check(health.check_database)


def test_health_ok_when_database_up(client: TestClient) -> None:
    health.set_db_check(lambda: True)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == __version__
    assert body["checks"] == {"application": "ok", "database": "ok"}


def test_health_503_when_database_down(client: TestClient) -> None:
    health.set_db_check(lambda: False)
    resp = client.get("/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "down"
