"""Financing-option matching.

A pure module: given a (synthetic) lender catalog and a small set of
business metrics already computed by the deterministic engine, return a
ranked list of financing matches. The module never calls an LLM, never
calculates anything outside the documented formulas (annuity repayment +
DSCR), and never reads from the database.

Hard rules (mandatory, override ranking):

- If the projected cash shortfall is non-positive, the module returns
  a single "no financing needed" sentinel — no further work, no
  ranking, no recommendations. The user is told the reason.
- A product whose hard eligibility checks fail is listed as
  ``not_recommended`` (still returned for transparency), regardless of
  any other ranking signal.
- A product whose DSCR (operating_profit / monthly_repayment) is below
  1.0 is listed as ``not_recommended`` even if all eligibility checks
  pass — the business cannot safely service the debt from current profit.

Ranking (within the ``possible`` and ``recommended`` tiers):

- DSCR highest first (capacity to repay with comfortable buffer).
- Then by closeness of the requested amount to a product's range mid-point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from app.engine.alerts import MonthlyCashPoint
from app.services.finance.money import ZERO, quantize


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinancingProduct:
    """One product from the synthetic catalog."""

    id: str
    name: str
    type: str
    min_amount: Decimal
    max_amount: Decimal
    min_months_operating: int
    min_avg_monthly_revenue: Decimal
    max_term_months: int
    indicative_annual_rate: Decimal
    suitable_use_cases: tuple[str, ...]
    synthetic: bool = True

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FinancingProduct":
        return cls(
            id=str(payload["id"]),
            name=str(payload["name"]),
            type=str(payload.get("type", "unknown")),
            min_amount=Decimal(str(payload["min_amount"])),
            max_amount=Decimal(str(payload["max_amount"])),
            min_months_operating=int(payload["min_months_operating"]),
            min_avg_monthly_revenue=Decimal(str(payload["min_avg_monthly_revenue"])),
            max_term_months=int(payload["max_term_months"]),
            indicative_annual_rate=Decimal(str(payload["indicative_annual_rate"])),
            suitable_use_cases=tuple(payload.get("suitable_use_cases", []) or []),
            synthetic=bool(payload.get("synthetic", True)),
        )


def load_catalog(path: str | Path) -> tuple[list[FinancingProduct], dict[str, Any]]:
    """Load a catalog from disk. Returns ``(products, raw_metadata)``.

    Raises :class:`ValueError` if any product has invalid numeric values.
    The function never silently coerces — bad catalog → loud error.
    """
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    products = [FinancingProduct.from_dict(p) for p in payload.get("products", [])]
    for p in products:
        if p.min_amount < ZERO:
            raise ValueError(f"product {p.id}: min_amount < 0")
        if p.max_amount < p.min_amount:
            raise ValueError(f"product {p.id}: max_amount < min_amount")
        if p.indicative_annual_rate < ZERO:
            raise ValueError(f"product {p.id}: indicative_annual_rate < 0")
        if p.max_term_months <= 0:
            raise ValueError(f"product {p.id}: max_term_months <= 0")
    metadata = {k: payload[k] for k in payload.keys() if k != "products"}
    return products, metadata


# ---------------------------------------------------------------------------
# Inputs to matching
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FinancingContext:
    """The deterministic inputs the matcher needs.

    Every number comes from the engine (or, in tests, from a hand-rolled
    equivalent). No field is optional in spirit, but every field has a
    documented default (``ZERO``) so callers can build minimal contexts
    in tests without ceremony.
    """

    currency: str
    funding_need: Decimal
    months_operating: int
    avg_monthly_revenue: Decimal
    monthly_operating_profit: Decimal
    # Optional: the cash trajectory used to derive funding_need; kept for
    # transparency, not used in ranking.
    monthly_cash: tuple[MonthlyCashPoint, ...] = field(default_factory=tuple)
    min_buffer: Decimal = Decimal("0")
    # Debt-service-coverage-ratio floor: 1.2 by default.
    min_dscr: Decimal = Decimal("1.2")


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


LABEL_RECOMMENDED = "recommended"
LABEL_POSSIBLE = "possible"
LABEL_NOT_RECOMMENDED = "not_recommended"

LABELS: tuple[str, ...] = (LABEL_RECOMMENDED, LABEL_POSSIBLE, LABEL_NOT_RECOMMENDED)


@dataclass(frozen=True)
class EligibilityCheck:
    name: str
    passed: bool
    requirement: str
    actual: str


@dataclass(frozen=True)
class ProductMatch:
    product_id: str
    product_name: str
    product_type: str
    label: str  # one of LABEL_*
    fit_reasons: tuple[str, ...]
    unmet_criteria: tuple[str, ...]
    checks: tuple[EligibilityCheck, ...]
    indicative_annual_rate: str
    requested_amount: str
    term_months: int
    monthly_repayment: str  # empty when not_recommended and no term computable
    dscr: str  # format: "operating_profit / monthly_repayment"; "" when not computable
    synthetic: bool = True


# ---------------------------------------------------------------------------
# Math primitives
# ---------------------------------------------------------------------------


def _annuity_monthly_payment(
    principal: Decimal,
    annual_rate: Decimal,
    term_months: int,
    currency: str,
) -> Decimal:
    """Standard amortising-loan annuity in ``Decimal``, rounded to currency precision.

    Formula::

        r = annual_rate / 12
        payment = principal * r / (1 - (1 + r) ** -term_months)

    When annual_rate is zero (interest-free), payment is straight-line:
    ``principal / term_months``. Handles ``term_months == 0`` defensively
    by returning ``0`` instead of raising.
    """
    if term_months <= 0:
        return ZERO
    r = annual_rate / Decimal(12)
    if r == ZERO:
        return quantize(principal / Decimal(term_months), currency)
    one_plus_r = Decimal(1) + r
    factor = one_plus_r ** (-term_months)
    payment = principal * r / (Decimal(1) - factor)
    return payment.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _dscr(operating_profit: Decimal, monthly_repayment: Decimal) -> Decimal | None:
    if monthly_repayment <= ZERO:
        return None
    return quantize(operating_profit / monthly_repayment, "USD")  # ratio, 2 dp is fine


def _format_ratio(value: Decimal | None) -> str:
    """Format a ratio to 4 decimal places, or empty string when None / undefined."""
    if value is None:
        return ""
    return f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


# ---------------------------------------------------------------------------
# Eligibility checks
# ---------------------------------------------------------------------------


def _check_amount(
    product: FinancingProduct, funding_need: Decimal, currency: str
) -> EligibilityCheck:
    actual = quantize(funding_need, currency)
    if actual < product.min_amount:
        return EligibilityCheck(
            name="funding_need_within_range",
            passed=False,
            requirement=f"between {product.min_amount} and {product.max_amount} {currency}",
            actual=f"{actual} {currency}",
        )
    if actual > product.max_amount:
        return EligibilityCheck(
            name="funding_need_within_range",
            passed=False,
            requirement=f"between {product.min_amount} and {product.max_amount} {currency}",
            actual=f"{actual} {currency}",
        )
    return EligibilityCheck(
        name="funding_need_within_range",
        passed=True,
        requirement=f"between {product.min_amount} and {product.max_amount} {currency}",
        actual=f"{actual} {currency}",
    )


def _check_months_operating(
    product: FinancingProduct, months_operating: int
) -> EligibilityCheck:
    return EligibilityCheck(
        name="months_operating",
        passed=months_operating >= product.min_months_operating,
        requirement=f">= {product.min_months_operating} months",
        actual=f"{months_operating} months",
    )


def _check_avg_revenue(
    product: FinancingProduct, avg_monthly_revenue: Decimal, currency: str
) -> EligibilityCheck:
    actual = quantize(avg_monthly_revenue, currency)
    return EligibilityCheck(
        name="avg_monthly_revenue",
        passed=actual >= product.min_avg_monthly_revenue,
        requirement=f">= {product.min_avg_monthly_revenue} {currency}",
        actual=f"{actual} {currency}",
    )


def _check_term(product: FinancingProduct, term_months: int) -> EligibilityCheck:
    return EligibilityCheck(
        name="term_months",
        passed=1 <= term_months <= product.max_term_months,
        requirement=f"1..{product.max_term_months} months",
        actual=f"{term_months} months",
    )


# ---------------------------------------------------------------------------
# Main matcher
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NoFinancingNeeded:
    """Sentinel returned when the business does not actually need financing."""

    reason: str
    minimum_projected_cash: str
    funding_need: str


@dataclass(frozen=True)
class FinancingOutcome:
    """Either ``matches`` is the ranking result, or ``no_financing_needed`` is set.

    Exactly one of the two is populated. The API handler decides which
    shape to serialise.
    """

    currency: str
    funding_need: str
    minimum_projected_cash: str
    matches: tuple[ProductMatch, ...] = field(default_factory=tuple)
    no_financing_needed: NoFinancingNeeded | None = None
    catalog_disclaimer: str = (
        "SYNTHETIC catalog. Illustrative products. Not a credit decision, "
        "not a real lender offer, and not financial advice. The LLM and "
        "Laya do not participate in this matching."
    )


def _projected_shortfall(
    *,
    monthly_cash: tuple[MonthlyCashPoint, ...],
    min_buffer: Decimal,
) -> Decimal:
    """Largest projected cash shortfall + min_buffer, or 0 when none.

    The shortfall is the absolute value of the minimum projected closing
    cash across the trajectory, added to ``min_buffer`` so the user ends
    up with their stated cushion after financing.
    """
    if not monthly_cash:
        return ZERO
    minimum = min((p.closing_cash for p in monthly_cash), default=ZERO)
    if minimum >= ZERO:
        return ZERO
    shortfall = -minimum
    return quantize(shortfall + min_buffer, "USD")


def _min_buffer_default(currency: str) -> Decimal:
    return ZERO  # defaults; callers may override


def match_financing(
    *,
    context: FinancingContext,
    products: list[FinancingProduct],
) -> FinancingOutcome:
    """Compute the ranked matches.

    The function is pure — it does not touch I/O. Catalog loading and
    building the context are the caller's responsibility. This makes the
    function trivially testable with hand-rolled inputs.
    """
    if context.funding_need <= ZERO:
        minimum_str = (
            f"{min((p.closing_cash for p in context.monthly_cash), default=ZERO)}"
            if context.monthly_cash
            else "0"
        )
        return FinancingOutcome(
            currency=context.currency,
            funding_need="0",
            minimum_projected_cash=minimum_str,
            no_financing_needed=NoFinancingNeeded(
                reason="No projected cash shortfall. Financing not required.",
                minimum_projected_cash=minimum_str,
                funding_need="0",
            ),
        )

    funding_need = quantize(context.funding_need, context.currency)
    matches: list[ProductMatch] = []

    for p in products:
        amount_check = _check_amount(p, funding_need, context.currency)
        months_check = _check_months_operating(p, context.months_operating)
        revenue_check = _check_avg_revenue(p, context.avg_monthly_revenue, context.currency)

        # Heuristic: pick the shorter of (capped product max_term_months) or 12 months.
        # We don't have a user-supplied term; default to a 12-month facility, capped by max_term_months.
        chosen_term = min(12, p.max_term_months)
        term_check = _check_term(p, chosen_term)

        hard_pass = all(
            (amount_check.passed, months_check.passed, revenue_check.passed, term_check.passed)
        )
        checks = (amount_check, months_check, revenue_check, term_check)

        # Compute monthly repayment + DSCR.
        monthly_repayment = _annuity_monthly_payment(
            principal=funding_need,
            annual_rate=p.indicative_annual_rate,
            term_months=chosen_term,
            currency=context.currency,
        )
        dscr_value = _dscr(context.monthly_operating_profit, monthly_repayment)

        dscr_pass = (
            dscr_value is not None and dscr_value >= context.min_dscr
        ) and hard_pass

        if not hard_pass:
            label = LABEL_NOT_RECOMMENDED
        elif not dscr_pass:
            label = LABEL_NOT_RECOMMENDED
        elif dscr_value is not None and dscr_value >= context.min_dscr * Decimal("1.5"):
            # Plenty of headroom: well above the floor.
            label = LABEL_RECOMMENDED
        else:
            label = LABEL_POSSIBLE

        fit_reasons: list[str] = []
        unmet: list[str] = []
        for c in checks:
            if c.passed:
                fit_reasons.append(c.name)
            else:
                unmet.append(f"{c.name} (need {c.requirement}; have {c.actual})")

        if hard_pass and dscr_value is not None:
            if dscr_value >= context.min_dscr:
                fit_reasons.append(f"dscr >= {context.min_dscr}")
            else:
                unmet.append(
                    f"dscr_below_floor (need >= {context.min_dscr}; have {_format_ratio(dscr_value)})"
                )

        matches.append(
            ProductMatch(
                product_id=p.id,
                product_name=p.name,
                product_type=p.type,
                label=label,
                fit_reasons=tuple(fit_reasons),
                unmet_criteria=tuple(unmet),
                checks=checks,
                indicative_annual_rate=str(quantize(p.indicative_annual_rate, context.currency)),
                requested_amount=str(funding_need),
                term_months=chosen_term,
                monthly_repayment=str(quantize(monthly_repayment, context.currency)),
                dscr=_format_ratio(dscr_value),
                synthetic=p.synthetic,
            )
        )

    # Sort: recommended > possible > not_recommended; within tier, descending DSCR,
    # then ascending absolute distance from the product range midpoint.
    def _product_mid(p: FinancingProduct) -> Decimal:
        return quantize((p.min_amount + p.max_amount) / Decimal(2), context.currency)

    def distance_to_mid(m: ProductMatch) -> Decimal:
        prod = next(p for p in products if p.id == m.product_id)
        return abs(funding_need - _product_mid(prod))

    def rank_key(m: ProductMatch) -> tuple[int, Decimal, Decimal]:
        tier = (
            0 if m.label == LABEL_RECOMMENDED
            else 1 if m.label == LABEL_POSSIBLE
            else 2
        )
        # Higher DSCR = better; smaller distance = better.
        dscr_dec = Decimal(m.dscr) if m.dscr else Decimal("0")
        # We invert DSCR (negate) so larger DSCR sorts smaller in ascending sort.
        return (tier, -dscr_dec, distance_to_mid(m))

    matches.sort(key=rank_key)

    min_projected = min(
        (p.closing_cash for p in context.monthly_cash), default=ZERO
    )

    return FinancingOutcome(
        currency=context.currency,
        funding_need=str(funding_need),
        minimum_projected_cash=str(quantize(min_projected, context.currency)),
        matches=tuple(matches),
    )


def compute_funding_need_from_points(
    *,
    points: list[MonthlyCashPoint],
    min_buffer: Decimal | None = None,
) -> Decimal:
    """Convenience: compute the funding need from a trajectory.

    Helpers keep the API handler short. Min buffer default = 0.
    """
    buf = min_buffer if min_buffer is not None else ZERO
    return _projected_shortfall(
        monthly_cash=tuple(points),
        min_buffer=buf,
    )


__all__ = [
    "FinancingProduct",
    "FinancingContext",
    "FinancingOutcome",
    "NoFinancingNeeded",
    "ProductMatch",
    "EligibilityCheck",
    "LABEL_RECOMMENDED",
    "LABEL_POSSIBLE",
    "LABEL_NOT_RECOMMENDED",
    "LABELS",
    "load_catalog",
    "match_financing",
    "compute_funding_need_from_points",
    "_annuity_monthly_payment",
    "_projected_shortfall",
]
