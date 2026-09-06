"""Health endpoint.

Reports application and database health separately. The service never reports
itself healthy when a critical dependency (the database) is down (AGENTS.md §
Observability / spec §46): a failing DB check yields HTTP 503.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from alphadex import __version__
from alphadex.db import check_database

router = APIRouter(tags=["health"])

# Indirection so tests can override the DB check without a real database.
_db_check: Callable[[], bool] = check_database


def set_db_check(func: Callable[[], bool]) -> None:
    """Override the database health probe (used by tests)."""
    global _db_check
    _db_check = func


class HealthChecks(BaseModel):
    application: Literal["ok"] = "ok"
    database: Literal["ok", "down"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    checks: HealthChecks


@router.get("/health", response_model=HealthResponse)
def health(response: Response) -> HealthResponse:
    db_ok = _db_check()
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        version=__version__,
        checks=HealthChecks(database="ok" if db_ok else "down"),
    )
