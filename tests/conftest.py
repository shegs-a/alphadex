"""Shared pytest fixtures.

Unit/data-quality tests run against an in-memory SQLite database so they are fast,
deterministic, and need no external services (AGENTS.md §11). PostgreSQL is
exercised separately via Docker Compose and the migration check.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from alphadex.models import Base


@pytest.fixture()
def sqlite_engine() -> Iterator[Engine]:
    """A fresh in-memory SQLite engine with the full schema and FK/CHECK enforced."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _enable_sqlite_constraints(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def session(sqlite_engine: Engine) -> Iterator[Session]:
    factory = sessionmaker(bind=sqlite_engine, expire_on_commit=False)
    with factory() as sess:
        yield sess
