"""Business workspace model."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    industry: Mapped[str] = mapped_column(String(40), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    fiscal_year_start_month: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="en-US")
    min_cash_reserve: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal("0"))
    target_operating_margin: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.10")
    )
    max_unsold_inventory_exposure_pct: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, default=Decimal("0.20")
    )

    transactions = relationship("Transaction", back_populates="business", cascade="all, delete-orphan")
    scenarios = relationship("Scenario", back_populates="business", cascade="all, delete-orphan")
    imports = relationship("ImportJob", back_populates="business", cascade="all, delete-orphan")
    decisions = relationship("DecisionReport", back_populates="business", cascade="all, delete-orphan")
