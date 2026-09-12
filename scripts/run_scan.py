"""One-shot Opportunity Scanner entrypoint.

Runs a single screen over the current data and prints a summary. Ingest market data
(and optionally fundamentals) first so there is something to screen.

Usage:
    uv run python scripts/run_scan.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger
from alphadex.scanner.config import ScreenConfig
from alphadex.scanner.service import ScanService


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = ScreenConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = ScanService(session, config).run()
    finally:
        session.close()

    logger.info("scan_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
