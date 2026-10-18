"""Test configuration and shared fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the backend package is importable when pytest is invoked from the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def _set_test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin deterministic defaults so tests never depend on the developer's shell."""
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test_moneyplant.db")
    monkeypatch.setenv("SECRET_KEY", "test-secret-do-not-use-in-prod")
    # Disable Laya by default; tests that exercise the adapter inject their own provider.
    monkeypatch.setenv("LAYA_ENABLED", "0")
    # LLM providers default to misconfigured so adapter code never hits the network.
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:1")  # unprobeable
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
