"""Service (professional) adapter."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


class ServiceAdapter:
    industry = "service"

    required_keys = (
        "opening_cash",
        "billable_hours_capacity",
        "planned_billable_utilization_pct",
        "hourly_price",
        "labor_cost_per_hour",
    )

    def validate_inputs(self, payload: dict[str, Any]) -> None:
        for key in self.required_keys:
            if key not in payload or payload[key] in (None, ""):
                raise ValueError(f"Missing required service input: {key}")
        util = Decimal(str(payload["planned_billable_utilization_pct"]))
        if util < 0 or util > Decimal("1"):
            raise ValueError("planned_billable_utilization_pct must be between 0 and 1")
        try:
            price = Decimal(str(payload["hourly_price"]))
            if price <= 0:
                raise ValueError("hourly_price must be > 0")
        except Exception as exc:
            raise ValueError(f"Invalid hourly_price: {payload['hourly_price']!r}") from exc
        horizon = payload.get("horizon_months", 1)
        if not isinstance(horizon, int) or horizon < 1 or horizon > 36:
            raise ValueError("horizon_months must be an integer between 1 and 36")

    def default_business_goal(self) -> str:
        return "Maintain utilization, healthy contribution margin, and reliable cash collection."