"""Financial invariants.

The engine asserts these on every result. If any invariant fails, the
scenario result carries ``invariants_ok=False`` with a per-invariant
failure reason. The frontend and decision rules surface these explicitly
— a scenario with broken invariants is never labelled "proceed".
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.services.finance.money import ZERO, quantize
from app.services.finance.inventory import ManufacturingResult


@dataclass(frozen=True)
class InvariantCheck:
    name: str
    passed: bool
    detail: str


def assert_invariants(
    opening_cash: Decimal,
    closing_cash: Decimal,
    cash_inflows: Decimal,
    cash_outflows: Decimal,
    currency: str,
    *,
    units_sold: Decimal | None = None,
    units_produced: Decimal | None = None,
    material_used: Decimal | None = None,
    available_material: Decimal | None = None,
    feasible_production: Decimal | None = None,
    production_capacity: Decimal | None = None,
    revenue: Decimal | None = None,
    selling_price: Decimal | None = None,
) -> list[InvariantCheck]:
    """Assert the canonical invariants and return a list of check results.

    Each check is independent. The function never raises; it returns
    results so the caller can decide how to surface them.
    """
    out: list[InvariantCheck] = []
    expected_closing = quantize(opening_cash + cash_inflows - cash_outflows, currency)
    out.append(
        InvariantCheck(
            name="closing_cash_equals_opening_plus_net_cash",
            passed=expected_closing == closing_cash,
            detail=f"opening={opening_cash} + inflows={cash_inflows} − outflows={cash_outflows} → expected {expected_closing}; got {closing_cash}",
        )
    )

    if units_sold is not None and units_produced is not None:
        out.append(
            InvariantCheck(
                name="units_sold_le_units_produced",
                passed=units_sold <= units_produced,
                detail=f"units_sold={units_sold}, units_produced={units_produced}",
            )
        )
    if material_used is not None and available_material is not None:
        out.append(
            InvariantCheck(
                name="material_used_le_available",
                passed=material_used <= available_material,
                detail=f"material_used={material_used}, available={available_material}",
            )
        )
    if feasible_production is not None and production_capacity is not None:
        out.append(
            InvariantCheck(
                name="feasible_production_le_capacity",
                passed=feasible_production <= production_capacity,
                detail=f"feasible={feasible_production}, capacity={production_capacity}",
            )
        )
    if revenue is not None and units_sold is not None and selling_price is not None:
        expected_rev = quantize(units_sold * selling_price, currency)
        out.append(
            InvariantCheck(
                name="revenue_equals_units_sold_times_price",
                passed=expected_rev == revenue,
                detail=f"expected {expected_rev} (units_sold × price); got {revenue}",
            )
        )
    return out


def all_passed(results: list[InvariantCheck]) -> bool:
    return all(r.passed for r in results)


def failures(results: list[InvariantCheck]) -> list[InvariantCheck]:
    return [r for r in results if not r.passed]


__all__ = ["InvariantCheck", "assert_invariants", "all_passed", "failures"]