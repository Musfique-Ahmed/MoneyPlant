"""Provider factory and selection."""

from __future__ import annotations

from app.core.config import get_settings
from app.services.llm.base import ExplanationProvider, ProviderMode
from app.services.llm.ollama_provider import OllamaProvider
from app.services.llm.openai_provider import OpenAIProvider
from app.services.llm.anthropic_provider import AnthropicProvider


def get_provider(mode: str | None = None) -> ExplanationProvider:
    """Return the provider for the given mode (or the configured default)."""
    settings = get_settings()
    effective = (mode or settings.ai_default_mode).lower()
    if effective == ProviderMode.LOCAL.value:
        return OllamaProvider()
    if effective == ProviderMode.OPENAI.value:
        return OpenAIProvider()
    if effective == ProviderMode.ANTHROPIC.value:
        return AnthropicProvider()
    return OllamaProvider()


def list_providers() -> list[ExplanationProvider]:
    return [OllamaProvider(), OpenAIProvider(), AnthropicProvider()]


__all__ = ["get_provider", "list_providers"]