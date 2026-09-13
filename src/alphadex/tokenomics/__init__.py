"""Tokenomics module — Token Value Capture.

Answers "does protocol strength accrue to the token?" — dilution/float overhang and
whether fees/revenue reach holders (Fees ≠ Revenue ≠ Holders Revenue, §9). A pure
analytical layer over the internal data model; the ``value_capture_score`` is a
**component** feeding Sprint 07's Alpha Score, never the Alpha Score itself. Missing
inputs are explicit, never ``0`` (ADR-003).
"""
