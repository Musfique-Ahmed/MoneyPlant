"""Scenario + versioned result models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Scenario(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "scenarios"

    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")

    business = relationship("Business", back_populates="scenarios")
    versions = relationship(
        "ScenarioVersion", back_populates="scenario", cascade="all, delete-orphan", order_by="ScenarioVersion.version_number"
    )


class ScenarioVersion(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "scenario_versions"
    __table_args__ = (UniqueConstraint("scenario_id", "version_number", name="uq_scenario_version"),)

    scenario_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs_json: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(32), nullable=False, default="0.1.0")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    scenario = relationship("Scenario", back_populates="versions")
