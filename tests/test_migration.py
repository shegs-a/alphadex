"""Migration smoke test.

Runs the Alembic migration end-to-end against a throwaway SQLite database and
verifies the expected tables are created and dropped. This proves the migration is
executable and reversible without requiring a running PostgreSQL instance.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from alphadex.config import get_settings

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def sqlite_db_url(tmp_path: Path) -> Iterator[str]:
    db_path = tmp_path / "migration_test.db"
    url = f"sqlite:///{db_path}"
    prev = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()  # env.py reads settings; force a re-read
    try:
        yield url
    finally:
        if prev is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = prev
        get_settings.cache_clear()


def _alembic_config() -> Config:
    return Config(str(REPO_ROOT / "alembic.ini"))


def test_migration_creates_and_drops_tables(sqlite_db_url: str) -> None:
    cfg = _alembic_config()

    command.upgrade(cfg, "head")
    engine = create_engine(sqlite_db_url)
    tables = set(inspect(engine).get_table_names())
    assert {
        "assets",
        "metric_observations",
        "asset_source_ids",
        "ingestion_runs",
        "scan_runs",
        "scan_results",
    }.issubset(tables)
    engine.dispose()

    command.downgrade(cfg, "base")
    engine = create_engine(sqlite_db_url)
    tables = set(inspect(engine).get_table_names())
    assert "assets" not in tables
    assert "metric_observations" not in tables
    assert "asset_source_ids" not in tables
    assert "ingestion_runs" not in tables
    assert "scan_runs" not in tables
    assert "scan_results" not in tables
    engine.dispose()
