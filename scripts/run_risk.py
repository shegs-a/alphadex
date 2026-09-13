"""One-shot Risk run over the analysis set (a separate output from Alpha, §10).

Ingest market + fundamentals and run a scan first so there are candidates.

Usage:
    uv run python scripts/run_risk.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger
from alphadex.risk.config import RiskConfig
from alphadex.risk.service import RiskService


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = RiskConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = RiskService(session, config).run()
    finally:
        session.close()

    logger.info("risk_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
