"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from alphadex import __version__
from alphadex.api.routes import (
    assets,
    fundamentals,
    health,
    market_data,
    opportunities,
)
from alphadex.config import get_settings
from alphadex.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.app_log_level)

    app = FastAPI(
        title="AlphaDex Scout",
        version=__version__,
        summary="Crypto Alpha Intelligence System — Ciphercrib Solutions",
    )
    app.include_router(health.router)
    app.include_router(assets.router)
    app.include_router(market_data.router)
    app.include_router(fundamentals.router)
    app.include_router(opportunities.router)
    return app


app = create_app()
