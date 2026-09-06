"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI

from alphadex import __version__
from alphadex.api.routes import health
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
    return app


app = create_app()
