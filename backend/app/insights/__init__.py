"""Deterministic, pure-function dashboard insights.

Each visual on the dashboard gets a small generator that consumes
already-computed engine numbers and emits a fixed-shape :class:`Visual`
record. No LLM, no float, no I/O. Every figure quoted in a sentence is
recomputed from the input; the API layer never has to re-format them.

The module is consumed by ``app/api/insights.py`` and the endpoint
``GET /api/businesses/{id}/dashboard-insights``.
"""
from app.insights.engine import (
    Visual,
    build_dashboard_insights,
    compute_aggregates,
    DashboardInputs,
    MonthlyAggregate,
)

__all__ = [
    "Visual",
    "build_dashboard_insights",
    "compute_aggregates",
    "DashboardInputs",
    "MonthlyAggregate",
]