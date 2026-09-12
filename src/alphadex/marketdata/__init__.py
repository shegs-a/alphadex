"""Market Data module — fetch, normalize, persist, and read market metrics.

Depends only on the ``MarketDataProvider`` interface, never a concrete provider
(AGENTS.md §2). Raw provider data is validated and normalized into append-only
``MetricObservation`` rows with explicit missing-data semantics and provenance.
"""
