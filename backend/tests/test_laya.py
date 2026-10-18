"""Laya adapter tests.

The adapter is responsible for two contracts:
1. When Laya is not configured, it returns deterministic "unavailable" assessments.
2. When Laya IS configured but the underlying call fails (no checkpoint, bad model, etc.),
   it returns "unavailable" with a real reason — never a fabricated answer.

The success path is verified by unit-injecting a fake predict function so the test
never depends on the network or a downloaded checkpoint.
"""

from __future__ import annotations

import pytest

import app.services.laya.adapter as adapter
from app.core.config import get_settings


def _reset_settings_cache() -> None:
    get_settings.cache_clear()


def test_assess_returns_unavailable_when_laya_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAYA_MODEL", "")
    _reset_settings_cache()

    out = adapter.assess_scenario(
        scenario_result_dict={"industry": "manufacturing", "revenue": "1000", "operating_profit": "200", "closing_cash": "500"},
        rule_evaluations=[],
        business_goal=None,
    )
    assert len(out) == 3
    assert all(a.status == "unavailable" for a in out)
    # Reasons are populated, not silent
    assert all(a.reason for a in out)
    # All three question_ids are covered
    qids = {a.question_id for a in out}
    assert qids == {"risk_category", "feasibility_score", "aligns_with_goal"}


def test_assess_returns_unavailable_when_predict_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAYA_MODEL", "fake-model-just-so-configured")
    _reset_settings_cache()

    def fake_laya_predict(state, questions, model, max_len):  # noqa: ARG001
        raise RuntimeError("checkpoint not found")

    monkeypatch.setattr(adapter, "_laya_predict", fake_laya_predict)

    out = adapter.assess_scenario(
        scenario_result_dict={"industry": "retail", "revenue": "0"},
        rule_evaluations=[],
        business_goal=None,
    )
    assert len(out) == 3
    for a in out:
        assert a.status == "unavailable"
        assert a.reason and "checkpoint not found" in a.reason
        assert a.model_id == "fake-model-just-so-configured"


def test_assess_normalizes_dict_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LAYA_MODEL", "configured-model")
    _reset_settings_cache()

    def fake_predict(state, questions, model, max_len):  # noqa: ARG001
        return {
            "answers": [
                {"label": "medium", "score": 0.55, "probability": 0.7},
                {"label": "4"},
                {"label": "yes", "confidence": 0.9},
            ],
            "routing": {"model": "configured-model@1"},
        }

    monkeypatch.setattr(adapter, "_laya_predict", fake_predict)

    out = adapter.assess_scenario(
        scenario_result_dict={"industry": "manufacturing", "revenue": "100"},
        rule_evaluations=[],
        business_goal="keep margin above 10%",
    )
    assert len(out) == 3
    a = out[0]
    assert a.status == "ok"
    assert a.answer_label == "medium"
    assert a.answer_score == 0.55
    assert a.answer_probability == 0.7
    assert a.model_id == "configured-model@1"

    # alignment question is normalised too
    align = next(x for x in out if x.question_id == "aligns_with_goal")
    assert align.status == "ok"
    assert align.answer_label == "yes"
    assert align.answer_probability == 0.9


def test_default_questions_cover_three_domains() -> None:
    qs = adapter.default_questions("manufacturing")
    qids = {q.question_id for q in qs}
    assert qids == {"risk_category", "feasibility_score", "aligns_with_goal"}
    # Options are present on the choice question
    choice = next(q for q in qs if q.question_id == "risk_category")
    assert choice.options == ["low", "medium", "high"]


def test_build_state_does_not_leak_internal_field_names() -> None:
    """The state we send to Laya is a curated subset, not raw rows."""
    state = adapter._build_state(
        result_dict={
            "industry": "manufacturing",
            "revenue": "100",
            "operating_profit": "20",
            "closing_cash": "200",
            "minimum_projected_cash": "100",
            "contribution_margin": "50",
            "warnings": ["some warning"],
        },
        rule_outcomes=[{"rule_id": "MIN_CASH_RESERVE", "status": "passed"}],
        business_goal="keep margin above 10%",
    )
    assert state["scenario"]["industry"] == "manufacturing"
    assert state["scenario"]["revenue"] == "100"
    assert state["rules"] == [{"rule_id": "MIN_CASH_RESERVE", "status": "passed"}]
    assert state["business_goal"] == "keep margin above 10%"
