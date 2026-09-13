"""Shared building blocks for the analytical engines.

Small, reusable pieces so each analytical engine (Tokenomics, Risk, …) does not
re-implement candidate selection and per-asset failure isolation. Introduced in
Sprint 06; the existing Scanner/Divergence services can migrate to it later (their
behavior is unchanged for now).
"""
