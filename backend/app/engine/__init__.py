"""Deterministic, pure-function derived features.

These modules take already-computed engine results and turn them into
user-facing signals (alerts, financing matches). They never call an LLM,
never call Laya, never touch the database, and never use ``float`` —
monetary values are ``decimal.Decimal`` throughout.
"""
