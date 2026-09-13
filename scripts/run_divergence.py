"""One-shot Economic Divergence Engine entrypoint.

Runs a single divergence pass over the analysis set (the Scanner's candidates by
default) and prints a summary. Ingest market + fundamentals and run a scan first;
running ingestion repeatedly over time enriches the cross-time (Track B) signal.

Usage:
    uv run python scripts/run_divergence.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.divergence.config import DivergenceConfig
from alphadex.divergence.service import DivergenceService
from alphadex.logging import configure_logging, get_logger


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = DivergenceConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = DivergenceService(session, config).run()
    finally:
        session.close()

    logger.info("divergence_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
