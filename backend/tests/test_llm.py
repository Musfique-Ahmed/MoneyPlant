"""LLM provider tests.

Two contracts under test:

1. ``health_check`` always reflects a real probe. If the local server isn't
   reachable, the result is ``unavailable`` with a real reason — never a
   silent green tick.
2. ``explain`` validates the provider response. A non-JSON or empty
   response becomes ``Explanation(status="unavailable")``, not a fabricated
   "ok" with empty fields.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.core.config import get_settings
from app.services.llm.base import (
    Capabilities,
    Explanation,
    ExplanationContext,
    ExplanationProvider,
    ProviderHealth,
    ProviderMode,
    ProviderStatus,
)
from app.services.llm.factory import get_provider, list_providers
from app.services.llm.ollama_provider import (
    OllamaProvider,
    _extract_json_object,
    _to_explanation,
)


def _reset_settings_cache() -> None:
    get_settings.cache_clear()


def test_health_check_reports_unavailable_when_local_server_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_LOCAL_BASE_URL", "http://127.0.0.1:1")  # unprobeable port
    _reset_settings_cache()

    p = OllamaProvider()
    h = p.health_check()
    assert h.mode == ProviderMode.LOCAL
    assert h.status in (ProviderStatus.UNAVAILABLE, ProviderStatus.MISCONFIGURED)
    # detail is populated with the underlying error
    assert h.detail is not None
    # Latency is still reported (even on failure)
    assert h.latency_ms is not None


def test_health_check_reports_ok_when_client_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch the client to a fake one that returns a successful models.list() call."""

    class _FakeModels:
        @staticmethod
        def list():  # noqa: D401
            return iter([])

    class _FakeClient:
        models = _FakeModels

    p = OllamaProvider()
    monkeypatch.setattr(p, "_ensure_client", lambda: _FakeClient())
    h = p.health_check()
    assert h.status == ProviderStatus.OK
    assert h.latency_ms is not None
    assert h.latency_ms >= 0


def test_extract_json_handles_fenced_and_bare() -> None:
    assert _extract_json_object('{"a": 1}') == {"a": 1}
    assert _extract_json_object('noise before ```json\n{"b": 2}\n``` noise after') == {"b": 2}
    assert _extract_json_object('not json at all') is None
    assert _extract_json_object('') is None
    # When the surrounding text isn't JSON but contains a JSON object, recover it.
    assert _extract_json_object('leading text {"k": "v"} trailing text') == {"k": "v"}


def test_to_explanation_handles_missing_and_string_fields() -> None:
    parsed: dict[str, Any] = {
        "summary": "ok",
        "recommendation": "go",
        "supporting_evidence": "a single string",
        "key_risks": ["r1", "r2"],
        "assumptions": [],
        "missing_information": [],
        "alternatives": [],
        "next_actions": [],
        "limitations": [],
    }
    e = _to_explanation(parsed, "test", "test-model", ProviderMode.LOCAL)
    assert e.status == "ok"
    assert e.summary == "ok"
    assert e.recommendation == "go"
    assert e.supporting_evidence == ["a single string"]
    assert e.key_risks == ["r1", "r2"]


def test_explain_returns_unavailable_on_unparseable_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the model returns non-JSON, we must return unavailable, not a coerced 'ok'."""

    class _FakeCompletions:
        def create(self, **kwargs):  # noqa: ARG002
            class _Resp:
                choices = [type("C", (), {"message": type("M", (), {"content": "not json at all"})()})()]
            return _Resp()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    p = OllamaProvider()
    monkeypatch.setattr(p, "_ensure_client", lambda: _FakeClient())
    monkeypatch.setattr(p, "health_check", lambda: ProviderHealth(
        mode=ProviderMode.LOCAL,
        status=ProviderStatus.OK,
        model="test-model",
        checked_at=p._settings.laya_model,  # any datetime
    ) if False else ProviderHealth(
        mode=ProviderMode.LOCAL,
        status=ProviderStatus.OK,
        model="test-model",
        checked_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    ))
    ctx = ExplanationContext(
        business_industry="manufacturing",
        reporting_period="2026-01",
        user_question="What should I do?",
        computed_baseline={"revenue": "0"},
        computed_scenarios=[],
        rule_evaluations=[],
        laya_assessment=None,
        assumptions=[],
        missing_information=[],
        business_goal=None,
    )
    out = p.explain(ctx)
    assert out.status == "unavailable"
    assert "could not be parsed" in (out.reason or "").lower()


def test_explain_returns_ok_on_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "summary": "All good",
        "recommendation": "Proceed",
        "supporting_evidence": ["x"],
        "key_risks": ["y"],
        "assumptions": [],
        "missing_information": [],
        "alternatives": [],
        "next_actions": [],
        "limitations": [],
    }

    class _FakeCompletions:
        def create(self, **kwargs):  # noqa: ARG002
            content = json.dumps(payload)
            message = type("M", (), {"content": content})()
            choice = type("C", (), {"message": message})()
            return type("R", (), {"choices": [choice]})()

    class _FakeChat:
        completions = _FakeCompletions()

    class _FakeClient:
        chat = _FakeChat()

    p = OllamaProvider()
    monkeypatch.setattr(p, "_ensure_client", lambda: _FakeClient())
    from datetime import datetime, timezone
    monkeypatch.setattr(p, "health_check", lambda: ProviderHealth(
        mode=ProviderMode.LOCAL,
        status=ProviderStatus.OK,
        model="test-model",
        checked_at=datetime.now(timezone.utc),
    ))
    ctx = ExplanationContext(
        business_industry="manufacturing",
        reporting_period="2026-01",
        user_question="q",
        computed_baseline={},
        computed_scenarios=[],
        rule_evaluations=[],
        laya_assessment=None,
        assumptions=[],
        missing_information=[],
        business_goal=None,
    )
    out = p.explain(ctx)
    assert out.status == "ok"
    assert out.summary == "All good"
    assert out.recommendation == "Proceed"
    assert out.supporting_evidence == ["x"]


def test_factory_returns_correct_provider_by_mode() -> None:
    assert get_provider("local").mode == ProviderMode.LOCAL
    assert get_provider("openai").mode == ProviderMode.OPENAI
    assert get_provider("anthropic").mode == ProviderMode.ANTHROPIC
    # Unknown mode defaults to local
    assert get_provider("nonsense").mode == ProviderMode.LOCAL


def test_list_providers_returns_all_three() -> None:
    modes = {p.mode for p in list_providers()}
    assert modes == {ProviderMode.LOCAL, ProviderMode.OPENAI, ProviderMode.ANTHROPIC}
