"""Fundamental Data module — fetch, normalize, persist, and read protocol economics.

Depends only on the ``FundamentalDataProvider`` interface, never a concrete provider
(AGENTS.md §2). Fees, revenue, holders-revenue, and TVL are stored as distinct
``fundamental.*`` observations with explicit missing-data and provenance, and are
never conflated with each other or with ``market.*`` price data (AGENTS.md §9).
"""
