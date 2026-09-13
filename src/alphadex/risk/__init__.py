"""Risk module — a separate Risk output (§10).

Assesses what can invalidate a thesis (liquidity, volatility, dilution, size), each a
distinct factor, blended into a Risk Score and band. This is **not** part of the Alpha
Score — a strong divergence with unacceptable risk is not a top candidate. Holder
concentration is ``NOT_AVAILABLE`` (no on-chain provider yet) — a data gap surfaced,
never guessed. Missing inputs are explicit, never ``0`` (ADR-003).
"""
