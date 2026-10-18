"""Industry adapters.

Each adapter exposes:

- ``extension_fields(industry)``: the extra Pydantic fields that the
  industry's scenario inputs add on top of the common ones.
- ``validate_inputs(payload)``: a typed pre-flight check that raises
  :class:`ValueError` with a human-readable message when the user's
  inputs are inconsistent.
- ``default_business_goal(industry)``: a string used as the LLM context's
  default goal when the user hasn't supplied one.

Adapters are pure — they don't import FastAPI, the database, or the LLM
layer. The runner combines the adapter output with the financial engine.
"""

from app.services.industry_adapters.base import IndustryAdapter
from app.services.industry_adapters.manufacturing import ManufacturingAdapter
from app.services.industry_adapters.inventory_based import (
    FoodAdapter,
    RetailAdapter,
    WholesaleAdapter,
)
from app.services.industry_adapters.service import ServiceAdapter

ADAPTERS: dict[str, IndustryAdapter] = {
    "manufacturing": ManufacturingAdapter(),
    "retail": RetailAdapter(),
    "wholesale": WholesaleAdapter(),
    "food": FoodAdapter(),
    "service": ServiceAdapter(),
}


def get_adapter(industry: str) -> IndustryAdapter:
    return ADAPTERS[industry]


__all__ = ["IndustryAdapter", "get_adapter", "ADAPTERS"]