"""AI endpoints — provider listing, health, and the assistant chat endpoint."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.business import Business
from app.schemas.business import BusinessRead, Industry
from app.schemas.llm import Explanation, ExplanationContext
from app.schemas.money import Currency
from app.services.llm.factory import get_provider, list_providers

router = APIRouter(prefix="/ai", tags=["ai"])


# --- assistant chat -------------------------------------------------------


class AssistantChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_id: str
    user_question: str = Field(min_length=1, max_length=2000)
    provider_mode: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AssistantChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    explanation: Explanation
    provider: str
    model: str
    mode: str


def _business_to_read(b: Business) -> BusinessRead:
    return BusinessRead(
        id=b.id,
        name=b.name,
        industry=Industry(b.industry),
        currency=Currency(b.currency),
        fiscal_year_start_month=b.fiscal_year_start_month,
        locale=b.locale,
        min_cash_reserve=str(b.min_cash_reserve),
        target_operating_margin=str(b.target_operating_margin),
        max_unsold_inventory_exposure_pct=str(b.max_unsold_inventory_exposure_pct),
        created_at=b.created_at,
        updated_at=b.updated_at,
    )


# --- routes ---------------------------------------------------------------


@router.get("/providers", response_model=list[dict[str, Any]])
def get_providers() -> list[dict[str, Any]]:
    """List every provider (name, mode, model, capabilities) for the UI."""
    out: list[dict[str, Any]] = []
    for p in list_providers():
        caps = p.get_capabilities()
        out.append(
            {
                "name": p.name,
                "mode": p.mode.value,
                "capabilities": caps.model_dump(),
            }
        )
    return out


@router.get("/health", response_model=list[dict[str, Any]])
def health() -> list[dict[str, Any]]:
    """Probe every provider and return its health snapshot.

    No provider call is silent: a green tick requires a successful real
    probe. ``ok`` is reserved for verified availability; everything else
    is ``unavailable`` or ``misconfigured`` with a reason.
    """
    out: list[dict[str, Any]] = []
    for p in list_providers():
        h = p.health_check()
        out.append(h.model_dump())
    return out


@router.post("/assistant/chat", response_model=AssistantChatResponse)
def assistant_chat(payload: AssistantChatRequest, db: Session = Depends(get_db)) -> AssistantChatResponse:
    """Send the user's question to the active LLM provider with a compact context."""
    business = db.get(Business, payload.business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="business_not_found")
    biz = _business_to_read(business)
    provider = get_provider(payload.provider_mode)
    explanation = provider.explain(
        ExplanationContext.model_validate(
            {
                "business_industry": biz.industry.value,
                "reporting_period": "ad_hoc",
                "user_question": payload.user_question,
                "computed_baseline": payload.context.get("computed_baseline", {}),
                "computed_scenarios": payload.context.get("computed_scenarios", []),
                "rule_evaluations": payload.context.get("rule_evaluations", []),
                "laya_assessment": payload.context.get("laya_assessment"),
                "assumptions": payload.context.get("assumptions", []),
                "missing_information": payload.context.get("missing_information", []),
                "business_goal": payload.context.get("business_goal"),
            }
        )
    )
    return AssistantChatResponse(
        explanation=explanation,
        provider=explanation.provider,
        model=explanation.model,
        mode=explanation.mode.value,
    )


__all__ = ["router", "AssistantChatRequest", "AssistantChatResponse"]
