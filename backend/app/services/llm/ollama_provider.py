"""Ollama local provider.

Targets ``http://localhost:11434/v1`` (OpenAI-compatible). Uses the
``openai`` Python SDK with a fake API key, which works with Ollama's
OpenAI-compatible endpoint.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

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

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are MoneyPlant's financial-explanation assistant. You explain computed business metrics, decision-rule outcomes, and scenario results to a small-business owner. You MUST:

- Refer only to the supplied computed metrics and explicit assumptions. Never invent numbers.
- Distinguish historical facts, computed projections, and your interpretation.
- State when information is missing rather than guess.
- Use clear, non-jargon language. Suggest concrete next actions.
- Return your response as a JSON object with these keys exactly: summary, recommendation, supporting_evidence (array), key_risks (array), assumptions (array), missing_information (array), alternatives (array), next_actions (array), limitations (array).
"""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Tolerate code-fenced JSON. Return the first parseable JSON object or None."""
    import json
    import re

    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        try:
            return json.loads(fenced.group(1))
        except json.JSONDecodeError:
            pass
    # Try the whole text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Find first '{' and last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _to_explanation(parsed: dict[str, Any], provider: str, model: str, mode: ProviderMode) -> Explanation:
    def _list(key: str) -> list[str]:
        v = parsed.get(key)
        if isinstance(v, list):
            return [str(x) for x in v if str(x).strip()]
        if isinstance(v, str) and v.strip():
            return [v.strip()]
        return []

    return Explanation(
        status="ok",
        provider=provider,
        model=model,
        mode=mode,
        summary=str(parsed.get("summary") or "").strip() or None,
        recommendation=str(parsed.get("recommendation") or "").strip() or None,
        supporting_evidence=_list("supporting_evidence"),
        key_risks=_list("key_risks"),
        assumptions=_list("assumptions"),
        missing_information=_list("missing_information"),
        alternatives=_list("alternatives"),
        next_actions=_list("next_actions"),
        limitations=_list("limitations"),
        raw=parsed,
    )


class OllamaProvider:
    mode = ProviderMode.LOCAL
    name = "ollama"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            try:
                from openai import OpenAI  # type: ignore[import-not-found]
            except Exception as exc:  # noqa: BLE001
                logger.warning("openai SDK not importable: %s", exc)
                raise
            self._client = OpenAI(
                base_url=self._settings.ai_local_base_url,
                api_key="ollama",  # Ollama ignores the key but the SDK requires a non-empty string.
                timeout=self._settings.ai_timeout_seconds,
            )
        return self._client

    def health_check(self) -> ProviderHealth:
        start = time.time()
        try:
            client = self._ensure_client()
            client.models.list()
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.OK,
                model=self._settings.ai_local_model,
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.UNAVAILABLE,
                model=self._settings.ai_local_model,
                detail=str(exc),
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )

    def get_capabilities(self) -> Capabilities:
        return Capabilities(supports_chat=True, supports_structured_output=False, max_context_tokens=8192)

    def explain(self, context: ExplanationContext) -> Explanation:
        health = self.health_check()
        if health.status != ProviderStatus.OK:
            return Explanation(
                status="unavailable",
                reason=f"Local provider unavailable: {health.detail}",
                provider=self.name,
                model=self._settings.ai_local_model,
                mode=self.mode,
            )
        try:
            client = self._ensure_client()
            response = client.chat.completions.create(
                model=self._settings.ai_local_model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": context.user_question},
                ],
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("ollama chat failed: %s", exc)
            return Explanation(
                status="unavailable",
                reason=f"Ollama request failed: {exc}",
                provider=self.name,
                model=self._settings.ai_local_model,
                mode=self.mode,
            )
        text = ""
        try:
            text = response.choices[0].message.content or ""
        except (AttributeError, IndexError) as exc:
            return Explanation(
                status="unavailable",
                reason=f"Unexpected Ollama response shape: {exc}",
                provider=self.name,
                model=self._settings.ai_local_model,
                mode=self.mode,
            )
        parsed = _extract_json_object(text)
        if parsed is None:
            return Explanation(
                status="unavailable",
                reason="Ollama response could not be parsed as JSON.",
                provider=self.name,
                model=self._settings.ai_local_model,
                mode=self.mode,
                raw={"text": text},
            )
        return _to_explanation(parsed, provider=self.name, model=self._settings.ai_local_model, mode=self.mode)


__all__ = ["OllamaProvider"]