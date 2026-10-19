"""Pydantic schemas for the dashboard-insights endpoint.

Every numeric value is a string (Decimal-only backend). The frontend mirrors these
exactly with Zod in ``apps/web/lib/schemas.ts``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DashboardVisual(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visual_id: str
    title: str
    what_it_shows: str
    what_to_notice: list[str]
    why_it_matters: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class DashboardInsightsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    currency: str
    period_start: str
    period_end_exclusive: str
    calculation_timestamp: str
    note: str = (
        "Insights are generated deterministically by the engine from the imported "
        "transactions and saved scenarios. The LLM and Laya do not participate. "
        "If 'Explain in more detail' is enabled, the precomputed insights become the "
        "structured context for the LLM — they are not replaced."
    )
    visuals: list[DashboardVisual]
    alerts_count: int
    financing_counts: dict[str, int] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Top-level KPIs as already-formatted money strings (currency + amount). "
            "Mirrors FinancialSummary.headline but kept here to avoid a second round-trip."
        ),
    )


__all__ = ["DashboardVisual", "DashboardInsightsResponse"]
