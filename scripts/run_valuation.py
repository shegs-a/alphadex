"""One-shot Valuation run over the analysis set — a component feeding Alpha.

Ingest market + fundamentals and run a scan first so there are candidates. Run before
``scripts/run_alpha.py`` so Alpha can consume the latest valuation.

Usage:
    uv run python scripts/run_valuation.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger
from alphadex.valuation.config import ValuationConfig
from alphadex.valuation.service import ValuationService


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = ValuationConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = ValuationService(session, config).run()
    finally:
        session.close()

    logger.info("valuation_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
