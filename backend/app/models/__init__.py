"""SQLAlchemy ORM models.

All models are imported here so that ``Base.metadata`` is fully populated
when Alembic autogenerate (or any consumer) introspects it. Tables map 1:1
to ``docs/ARCHITECTURE.md`` §5.
"""

from app.models.business import Business
from app.models.decision import DecisionReport, LlmExplanation
from app.models.import_job import ImportJob
from app.models.scenario import Scenario, ScenarioVersion
from app.models.transaction import Transaction

__all__ = [
    "Business",
    "Transaction",
    "ImportJob",
    "Scenario",
    "ScenarioVersion",
    "DecisionReport",
    "LlmExplanation",
]
