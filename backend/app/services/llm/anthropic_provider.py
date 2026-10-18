"""Anthropic provider."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx

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

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-3-5-sonnet-latest"


class AnthropicProvider:
    mode = ProviderMode.ANTHROPIC
    name = "anthropic"

    def __init__(self) -> None:
        self._settings = get_settings()

    def health_check(self) -> ProviderHealth:
        start = time.time()
        if not self._settings.has_anthropic:
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.MISCONFIGURED,
                model=DEFAULT_MODEL,
                detail="ANTHROPIC_API_KEY is not set",
                latency_ms=0,
                checked_at=datetime.now(timezone.utc),
            )
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": self._settings.anthropic_api_key or "",
                        "anthropic-version": ANTHROPIC_VERSION,
                    },
                )
                r.raise_for_status()
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.OK,
                model=DEFAULT_MODEL,
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )
        except Exception as exc:  # noqa: BLE001
            latency = int((time.time() - start) * 1000)
            return ProviderHealth(
                mode=self.mode,
                status=ProviderStatus.UNAVAILABLE,
                model=DEFAULT_MODEL,
                detail=str(exc),
                latency_ms=latency,
                checked_at=datetime.now(timezone.utc),
            )

    def get_capabilities(self) -> Capabilities:
        return Capabilities(supports_chat=True, supports_structured_output=False, max_context_tokens=200000)

    def explain(self, context: ExplanationContext) -> Explanation:
        health = self.health_check()
        if health.status != ProviderStatus.OK:
            return Explanation(
                status="unavailable",
                reason=f"Anthropic provider unavailable: {health.detail}",
                provider=self.name,
                model=DEFAULT_MODEL,
                mode=self.mode,
            )
        try:
            with httpx.Client(timeout=float(self._settings.ai_timeout_seconds)) as client:
                r = client.post(
                    ANTHROPIC_API,
                    headers={
                        "x-api-key": self._settings.anthropic_api_key or "",
                        "anthropic-version": ANTHROPIC_VERSION,
                        "content-type": "application/json",
                    },
                    json={
                        "model": DEFAULT_MODEL,
                        "max_tokens": 1024,
                        "system": _SYSTEM_PROMPT,
                        "messages": [{"role": "user", "content": context.user_question}],
                    },
                )
                r.raise_for_status()
                data = r.json()
        except Exception as exc:  # noqa: BLE001
            return Explanation(
                status="unavailable",
                reason=f"Anthropic request failed: {exc}",
                provider=self.name,
                model=DEFAULT_MODEL,
                mode=self.mode,
            )
        # Anthropic returns content as a list of blocks; take the first text block.
        text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                text += block.get("text", "")
        parsed = _extract_json_object(text) or {}
        if not parsed:
            return Explanation(
                status="unavailable",
                reason="Anthropic response was not valid JSON.",
                provider=self.name,
                model=DEFAULT_MODEL,
                mode=self.mode,
                raw={"text": text, "raw_response": data},
            )
        return _to_explanation(parsed, provider=self.name, model=DEFAULT_MODEL, mode=self.mode)


__all__ = ["AnthropicProvider"]