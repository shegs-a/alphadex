"""One-shot Alpha Scoring run over the analysis set — the headline decision output.

Ingest market + fundamentals, then run scan → divergence → tokenomics → risk first so
the components exist. Alpha, Risk, and Confidence are three separate outputs (§10).

Usage:
    uv run python scripts/run_alpha.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict

from alphadex.alpha.config import AlphaConfig
from alphadex.alpha.service import AlphaService
from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger


def main() -> int:
    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    config = AlphaConfig.from_settings(settings)
    session = get_sessionmaker()()
    try:
        summary = AlphaService(session, config).run()
    finally:
        session.close()

    logger.info("alpha_summary", **asdict(summary))
    return 0 if summary.status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
