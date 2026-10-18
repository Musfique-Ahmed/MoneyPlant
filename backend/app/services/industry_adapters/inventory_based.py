"""Retail, wholesale, and food adapters.

All three are inventory-based; the differences are in industry-specific
copy and validation nuances.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class _InventoryAdapter:
    industry: str = ""

    required_keys = (
        "opening_cash",
        "opening_inventory_units",
        "planned_purchase_units",
        "purchase_unit_cost",
        "selling_price",
        "expected_units_sold",
    )

    def validate_inputs(self, payload: dict[str, Any]) -> None:
        for key in self.required_keys:
            if key not in payload or payload[key] in (None, ""):
                raise ValueError(f"Missing required input for {self.industry}: {key}")
        for key in ("opening_cash", "purchase_unit_cost", "selling_price"):
            try:
                d = Decimal(str(payload[key]))
                if d < 0:
                    raise ValueError(f"{key} must be >= 0")
            except Exception as exc:
                raise ValueError(f"Invalid decimal for {key}: {payload[key]!r}") from exc
        shrink = Decimal(str(payload.get("shrinkage_pct", "0")))
        if shrink < 0 or shrink > Decimal("0.5"):
            raise ValueError("shrinkage_pct must be between 0 and 0.5")
        horizon = payload.get("horizon_months", 1)
        if not isinstance(horizon, int) or horizon < 1 or horizon > 36:
            raise ValueError("horizon_months must be an integer between 1 and 36")

    def default_business_goal(self) -> str:
        return "Maintain margins and avoid stockouts while preserving cash."


class RetailAdapter(_InventoryAdapter):
    industry = "retail"

    def default_business_goal(self) -> str:
        return "Maintain sell-through, avoid stockouts, and protect margins."


class WholesaleAdapter(_InventoryAdapter):
    industry = "wholesale"

    def default_business_goal(self) -> str:
        return "Manage longer payment cycles, preserve cash, and protect volume margins."


class FoodAdapter(_InventoryAdapter):
    industry = "food"

    def default_business_goal(self) -> str:
        return "Hit food-cost targets, minimize waste, and preserve cash through slower-paying periods."