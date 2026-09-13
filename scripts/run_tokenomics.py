"""One-shot Tokenomics (Token Value Capture) run over the analysis set.

Ingest market + fundamentals and run a scan first so there are candidates.

Usage:
    uv run python scripts/run_tokenomics.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger
from alphadex.tokenomics.config import TokenomicsConfig
from alphadex.tokenomics.service import TokenomicsService


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = TokenomicsConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = TokenomicsService(session, config).run()
    finally:
        session.close()

    logger.info("tokenomics_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
