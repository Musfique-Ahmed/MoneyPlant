"""Manufacturing adapter — clothing / production example."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class ManufacturingAdapter:
    industry = "manufacturing"

    def validate_inputs(self, payload: dict[str, Any]) -> None:
        required = [
            "opening_cash",
            "opening_raw_material_qty",
            "planned_raw_material_purchase_qty",
            "material_unit_cost",
            "material_per_unit",
            "planned_production_qty",
            "production_capacity_qty",
            "labor_cost_per_unit",
            "selling_price",
            "expected_units_sold",
        ]
        for key in required:
            if key not in payload or payload[key] in (None, ""):
                raise ValueError(f"Missing required manufacturing input: {key}")

        def _dec(key: str) -> Decimal:
            try:
                return Decimal(str(payload[key]))
            except Exception as exc:
                raise ValueError(f"Invalid decimal for {key}: {payload[key]!r}") from exc

        if _dec("production_capacity_qty") <= 0:
            raise ValueError("production_capacity_qty must be > 0")
        if _dec("material_per_unit") < 0:
            raise ValueError("material_per_unit must be >= 0")
        if _dec("material_waste_pct") < 0 or _dec("material_waste_pct") > Decimal("0.5"):
            raise ValueError("material_waste_pct must be between 0 and 0.5")
        if _dec("selling_price") <= 0:
            raise ValueError("selling_price must be > 0")
        horizon = payload.get("horizon_months", 1)
        if not isinstance(horizon, int) or horizon < 1 or horizon > 36:
            raise ValueError("horizon_months must be an integer between 1 and 36")

    def default_business_goal(self) -> str:
        return "Maintain healthy cash reserve while meeting demand at acceptable margin."