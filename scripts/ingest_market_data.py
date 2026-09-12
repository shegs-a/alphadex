"""One-shot market-data ingestion entrypoint.

Runs a single fetch→normalize→persist cycle against the configured universe and
prints a summary. Scheduling (periodic runs) is intentionally out of scope for
Sprint 02 — this is operational tooling, not a public API.

Usage:
    uv run python scripts/ingest_market_data.py
    uv run python scripts/ingest_market_data.py --top-n 25
    uv run python scripts/ingest_market_data.py --ids bitcoin,ethereum,solana
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict

from alphadex.config import get_settings
from alphadex.db import get_sessionmaker
from alphadex.logging import configure_logging, get_logger
from alphadex.marketdata.service import MarketDataService
from alphadex.providers.factory import build_market_data_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest market data from a provider.")
    parser.add_argument(
        "--top-n",
        type=int,
        default=None,
        help="Fetch the top-N assets by market cap (overrides config).",
    )
    parser.add_argument(
        "--ids",
        type=str,
        default=None,
        help="Comma-separated provider ids to fetch (overrides top-N/config).",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(settings.app_log_level)
    logger = get_logger(__name__)

    ids = (
        [p.strip() for p in args.ids.split(",") if p.strip()]
        if args.ids
        else (settings.universe_ids or None)
    )
    top_n = args.top_n if args.top_n is not None else settings.market_universe_top_n

    provider = build_market_data_provider(settings)
    session = get_sessionmaker()()
    try:
        service = MarketDataService(provider, session)
        summary = service.ingest(ids=ids, top_n=top_n)
    finally:
        session.close()
        close = getattr(provider, "close", None)
        if callable(close):
            close()

    logger.info("ingest_summary", **asdict(summary))
    if summary.status == "failed":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
