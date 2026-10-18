"""Decision report and LLM explanation models."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class DecisionReport(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "decision_reports"

    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scenario_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scenario_versions.id", ondelete="CASCADE"), nullable=True
    )
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    overall_status: Mapped[str] = mapped_column(String(32), nullable=False)
    laya_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_used")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business = relationship("Business", back_populates="decisions")
    explanations = relationship("LlmExplanation", back_populates="decision_report", cascade="all, delete-orphan")


class LlmExplanation(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "llm_explanations"

    decision_report_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("decision_reports.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    content_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    decision_report = relationship("DecisionReport", back_populates="explanations")
