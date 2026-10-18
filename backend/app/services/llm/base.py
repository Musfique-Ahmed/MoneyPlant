"""Provider interface + explanation schema.

The provider returns a :class:`ProviderStatus` from ``health_check`` and
a validated :class:`Explanation` from ``explain``. Invalid responses
become ``Explanation(status="unavailable", ...)`` — never coerced.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel as _BaseModel


class ProviderMode(str, Enum):
    LOCAL = "local"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ProviderStatus(str, Enum):
    OK = "ok"
    UNAVAILABLE = "unavailable"
    MISCONFIGURED = "misconfigured"


class Capabilities(_BaseModel):  # type: ignore[no-redef]
    supports_chat: bool = True
    supports_structured_output: bool = True
    max_context_tokens: int = 8192


class ProviderHealth(_BaseModel):  # type: ignore[no-redef]
    mode: ProviderMode
    status: ProviderStatus
    model: str
    detail: str | None = None
    latency_ms: int | None = None
    checked_at: datetime


class Explanation(_BaseModel):  # type: ignore[no-redef]
    status: str  # "ok" | "unavailable"
    reason: str | None = None
    provider: str
    model: str
    mode: ProviderMode
    summary: str | None = None
    recommendation: str | None = None
    supporting_evidence: list[str] = []
    key_risks: list[str] = []
    assumptions: list[str] = []
    missing_information: list[str] = []
    alternatives: list[str] = []
    next_actions: list[str] = []
    limitations: list[str] = []
    raw: dict[str, Any] = {}


class ExplanationContext(_BaseModel):  # type: ignore[no-redef]
    """Compact context the provider receives. Raw transactions are never sent."""

    business_industry: str
    reporting_period: str
    user_question: str
    computed_baseline: dict[str, Any]
    computed_scenarios: list[dict[str, Any]]
    rule_evaluations: list[dict[str, Any]]
    laya_assessment: dict[str, Any] | None
    assumptions: list[str]
    missing_information: list[str]
    business_goal: str | None


class ExplanationProvider(Protocol):
    mode: ProviderMode
    name: str

    def explain(self, context: ExplanationContext) -> Explanation: ...
    def health_check(self) -> ProviderHealth: ...
    def get_capabilities(self) -> Capabilities: ...


__all__ = [
    "ProviderMode",
    "ProviderStatus",
    "ProviderHealth",
    "Explanation",
    "ExplanationContext",
    "ExplanationProvider",
    "Capabilities",
]