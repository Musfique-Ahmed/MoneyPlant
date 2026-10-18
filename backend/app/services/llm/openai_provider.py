"""OpenAI provider (also serves any OpenAI-API-compatible service)."""

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
    ProviderHealth,
    ProviderMode,
    ProviderStatus,
)
from app.services.llm.ollama_provider import _SYSTEM_PROMPT, _extract_json_object, _to_explanation

logger = logging.getLogger(__name__)


class OpenAIProvider:
    mode = ProviderMode.OPENAI
    name = "openai"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            if not self._settings.has_openai:
                raise RuntimeError("OPENAI_API_KEY is not set")
            from openai import OpenAI  # type: ignore[import-not-found]

            self._client = OpenAI(
                api_key=self._settings.openai_api_key,
                timeout=self._settings.ai_timeout_seconds,
            )
        return self._client

    def health_check(self) -> ProviderHealth:
        start = time.time()
        if not self._settings.has_openai:
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.MISCONFIGURED,
                model="gpt-4o-mini",
                detail="OPENAI_API_KEY is not set",
                latency_ms=0,
                checked_at=datetime.now(timezone.utc),
            )
        try:
            client = self._ensure_client()
            client.models.list()
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.OK,
                model="gpt-4o-mini",
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.UNAVAILABLE,
                model="gpt-4o-mini",
                detail=str(exc),
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )

    def get_capabilities(self) -> Capabilities:
        return Capabilities(supports_chat=True, supports_structured_output=True, max_context_tokens=128000)

    def explain(self, context: ExplanationContext) -> Explanation:
        health = self.health_check()
        if health.status != ProviderStatus.OK:
            return Explanation(
                status="unavailable",
                reason=f"OpenAI provider unavailable: {health.detail}",
                provider=self.name,
                model="gpt-4o-mini",
                mode=self.mode,
            )
        try:
            client = self._ensure_client()
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": context.user_question},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            text = response.choices[0].message.content or ""
        except Exception as exc:  # noqa: BLE001
            return Explanation(
                status="unavailable",
                reason=f"OpenAI request failed: {exc}",
                provider=self.name,
                model="gpt-4o-mini",
                mode=self.mode,
            )
        parsed = _extract_json_object(text) or {}
        if not parsed:
            return Explanation(
                status="unavailable",
                reason="OpenAI response was not valid JSON.",
                provider=self.name,
                model="gpt-4o-mini",
                mode=self.mode,
                raw={"text": text},
            )
        return _to_explanation(parsed, provider=self.name, model="gpt-4o-mini", mode=self.mode)


__all__ = ["OpenAIProvider"]