"""One-shot fundamentals ingestion entrypoint.

Runs a single fetch→match→normalize→persist cycle for protocol fundamentals and
prints a summary. Protocols are matched to assets already in the universe by
gecko_id (Phase 1); unmatched protocols are skipped. Ingest market data first so
there are assets to match against.

Usage:
    uv run python scripts/ingest_fundamentals.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.fundamentals.service import FundamentalDataService
from alphadex.logging import configure_logging, get_logger
from alphadex.providers.factory import build_fundamental_data_provider


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    provider = build_fundamental_data_provider(settings)
    session = get_sessionmaker()()
    try:
        service = FundamentalDataService(provider, session)
        summary = service.ingest()
    finally:
        session.close()
        close = getattr(provider, "close", None)
        if callable(close):
            close()

    logger.info("ingest_summary", **asdict(summary))
    return 1 if summary.status == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
