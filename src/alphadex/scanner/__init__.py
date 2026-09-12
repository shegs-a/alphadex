"""Opportunity Scanner — the cheap, broad screen at the top of the pipeline.

A pure analytical layer over the internal data model (AGENTS.md §2, §9): it reads
the latest ``market.*`` and ``fundamental.*`` observations, applies configurable
inclusion gates, computes a **preliminary** Screen Score (never the Alpha Score),
and persists a ranked, explainable candidate set. It fetches nothing external and
does not compute divergence, valuation, or risk (later sprints).
"""
