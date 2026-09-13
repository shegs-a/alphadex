"""Economic Divergence Engine — the heart of the thesis.

Detects where a protocol's economic fundamentals are improving faster than the
market's price/valuation recognizes (AGENTS.md §1). A pure analytical layer over the
internal data model: it reads observations (Track A growth windows and Track B
cross-time history) and the Scanner's candidates, and emits an explainable divergence
signal — a component, never the Alpha Score, and never blind BUY language (§10).
"""
