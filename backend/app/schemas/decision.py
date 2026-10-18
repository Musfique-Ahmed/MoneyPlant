"""Decision report + rule evaluation + Laya assessment schemas."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class RuleSeverity(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    INFO = "info"


class RuleStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    BREACHED = "breached"
    NOT_EVALUABLE = "not_evaluable"


class RuleEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_version: str
    name: str
    severity: RuleSeverity
    status: RuleStatus
    actual_value: str | None = None
    threshold: str | None = None
    unit: str | None = None
    explanation: str
    related_metric: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    corrective_action: str | None = None


class OverallStatus(str, Enum):
    PROCEED = "proceed"
    PROCEED_WITH_CAUTION = "proceed_with_caution"
    REVISE = "revise"
    INSUFFICIENT_DATA = "insufficient_data"
    REJECT = "reject"


class LayaQuestionKind(str, Enum):
    CHOICE = "choice"
    SCORE = "score"
    NOUL = "noul"


class LayaQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question_id: str
    kind: LayaQuestionKind
    text: str
    options: list[str] | None = None
    scale: tuple[int, int] | None = None


class LayaAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "unavailable"] = "ok"
    reason: str | None = None
    question_id: str
    answer_label: str
    answer_score: float | None = None
    answer_probability: float | None = None
    model_id: str
    raw_response: dict[str, Any] = Field(default_factory=dict)


class DecisionReportCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    scenario_version_id: str | None = None
    question: str = Field(min_length=1, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)


class DecisionReportRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    business_id: str
    scenario_version_id: str | None
    question: str
    overall_status: OverallStatus
    laya_status: str
    rule_evaluations: list[RuleEvaluation]
    laya_assessments: list[LayaAssessment]
    binding_constraints: list[str]
    key_risks: list[str]
    recommendation: str
    missing_information: list[str]
    assumptions: list[str]
    caveats: list[str]
    business_goal: str | None
    calculation_timestamp: datetime


class DecisionExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_mode: str | None = Field(
        default=None, description="Override the configured provider mode for this request."
    )


__all__ = [
    "RuleSeverity",
    "RuleStatus",
    "RuleEvaluation",
    "OverallStatus",
    "LayaQuestion",
    "LayaQuestionKind",
    "LayaAssessment",
    "DecisionReportCreate",
    "DecisionReportRead",
    "DecisionExplainRequest",
]
