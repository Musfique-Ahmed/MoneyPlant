"""Laya adapter implementation."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import get_settings
from app.schemas.decision import (
    LayaAssessment,
    LayaQuestion,
    LayaQuestionKind,
)

logger = logging.getLogger(__name__)


def _build_state(result_dict: dict[str, Any], rule_outcomes: list[dict[str, Any]], business_goal: str | None) -> dict[str, Any]:
    """Build a compact Laya state dict from a scenario result and rule evaluations.

    The shape mirrors the structure the Laya README example uses.
    """
    return {
        "scenario": {
            "industry": result_dict.get("industry"),
            "revenue": result_dict.get("revenue"),
            "operating_profit": result_dict.get("operating_profit"),
            "closing_cash": result_dict.get("closing_cash"),
            "minimum_projected_cash": result_dict.get("minimum_projected_cash"),
            "contribution_margin": result_dict.get("contribution_margin"),
            "warnings": result_dict.get("warnings", []),
        },
        "rules": rule_outcomes,
        "business_goal": business_goal,
    }


def default_questions(industry: str) -> list[LayaQuestion]:
    """Three bounded questions the engine asks Laya for every scenario.

    Each question is well-defined; the answers are constrained to a
    label set, a score range, or a yes/no probability.
    """
    return [
        LayaQuestion(
            question_id="risk_category",
            kind=LayaQuestionKind.CHOICE,
            text=f"For this {industry} scenario, which risk category best describes the projected outcome?",
            options=["low", "medium", "high"],
        ),
        LayaQuestion(
            question_id="feasibility_score",
            kind=LayaQuestionKind.SCORE,
            text="On a 1-5 scale, how feasible is the proposed plan?",
            scale=(1, 5),
        ),
        LayaQuestion(
            question_id="aligns_with_goal",
            kind=LayaQuestionKind.NOUL,
            text="Does this scenario align with the stated business goal?",
        ),
    ]


def _laya_predict(state: dict[str, Any], questions: list[dict[str, Any]], model: str, max_len: int) -> dict[str, Any]:
    """Call the real Laya API. Imports are deferred so the rest of the app can run without Laya installed."""
    from laya import Router  # type: ignore[import-not-found]

    router = Router()
    raw = router.predict(state=state, questions=questions, model=model, max_len=max_len)
    # The documented shape is {"answers": [...], "routing": {"model": "..."}}
    if isinstance(raw, dict) and "answers" in raw:
        return raw
    # Some Laya versions return an object with .answers
    if hasattr(raw, "answers"):
        return {"answers": list(raw.answers), "routing": getattr(raw, "routing", {})}
    return {"answers": list(raw) if isinstance(raw, list) else [], "routing": {}}


def _normalize_answer(question: LayaQuestion, raw: Any) -> tuple[str, float | None, float | None]:
    """Normalize a Laya answer for one question into (label, score, probability)."""
    if isinstance(raw, dict):
        label = str(raw.get("label") or raw.get("answer") or raw.get("text") or "")
        score = raw.get("score")
        prob = raw.get("probability") or raw.get("confidence")
        return (
            label,
            float(score) if isinstance(score, (int, float)) else None,
            float(prob) if isinstance(prob, (int, float)) else None,
        )
    if isinstance(raw, str):
        return raw, None, None
    if isinstance(raw, (int, float)):
        return str(raw), float(raw), None
    return "", None, None


def assess_scenario(
    scenario_result_dict: dict[str, Any],
    rule_evaluations: list[dict[str, Any]],
    business_goal: str | None,
) -> list[LayaAssessment]:
    """Run Laya on the scenario and return a list of normalized assessments.

    Returns a list of ``LayaAssessment(status="unavailable", ...)`` if
    Laya is not configured, the checkpoint is missing, or the call fails.
    """
    settings = get_settings()
    if not settings.has_laya:
        return [
            LayaAssessment(
                status="unavailable",
                reason="Laya is not configured (LAYA_MODEL is empty).",
                question_id=q.question_id,
                answer_label="unavailable",
                model_id="n/a",
            )
            for q in default_questions(scenario_result_dict.get("industry", "unknown"))
        ]

    state = _build_state(scenario_result_dict, rule_evaluations, business_goal)
    questions_models = default_questions(scenario_result_dict.get("industry", "unknown"))
    questions_payload = [
        {"id": q.question_id, "text": q.text, "options": q.options, "scale": q.scale, "kind": q.kind.value}
        for q in questions_models
    ]

    try:
        raw = _laya_predict(state, questions_payload, settings.laya_model, 8192)
    except Exception as exc:  # noqa: BLE001 — any failure here means "unavailable"
        logger.warning("laya.predict failed: %s", exc)
        return [
            LayaAssessment(
                status="unavailable",
                reason=f"Laya predict failed: {exc}",
                question_id=q.question_id,
                answer_label="unavailable",
                model_id=settings.laya_model or "n/a",
            )
            for q in questions_models
        ]

    answers = raw.get("answers") or []
    model_id = str((raw.get("routing") or {}).get("model") or settings.laya_model or "unknown")
    out: list[LayaAssessment] = []
    for q, raw_answer in zip(questions_models, answers, strict=False):
        label, score, prob = _normalize_answer(q, raw_answer)
        out.append(
            LayaAssessment(
                status="ok",
                question_id=q.question_id,
                answer_label=label,
                answer_score=score,
                answer_probability=prob,
                model_id=model_id,
                raw_response={"answer": raw_answer},
            )
        )
    return out


__all__ = ["assess_scenario", "default_questions"]