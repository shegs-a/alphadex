"""Database engine and session management (SQLAlchemy 2.0, sync).

A synchronous engine is used for simplicity at Scout scale (AGENTS.md §18:
operational simplicity / maintainability over performance). Async can be
introduced later if a concrete need arises.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from alphadex.config import get_settings

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the process-wide SQLAlchemy engine, creating it on first use."""
    global _engine, _SessionLocal
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.sqlalchemy_url,
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def get_sessionmaker() -> sessionmaker[Session]:
    """Return the configured session factory."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None  # for type-checkers
    return _SessionLocal


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a database session."""
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.close()


def check_database() -> bool:
    """Return True if the database answers a trivial query, else False."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def reset_engine_for_testing() -> None:
    """Dispose and clear the cached engine (used by tests to swap databases)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
