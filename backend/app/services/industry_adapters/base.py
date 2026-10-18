"""Adapter protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IndustryAdapter(ABC):
    """Protocol every adapter implements."""

    industry: str

    @abstractmethod
    def validate_inputs(self, payload: dict[str, Any]) -> None:
        """Raise :class:`ValueError` with a user-facing message if invalid."""

    @abstractmethod
    def default_business_goal(self) -> str:
        """Default business goal surfaced in the LLM context and the comparison summary."""