"""Transaction model: one financial record per row."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin


class Transaction(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "transactions"

    business_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tx_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cash_flow_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # inflow|outflow
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    payment_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    customer_or_supplier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_sheet: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    import_job_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
# Sync-dedup: SHA-256 over the canonical row tuple. Enforced unique per
    # business by ``uq_transactions_business_source_row_hash``. Allows
    # idempotent re-syncs.
    source_row_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Provenance: the DataSource that brought this row in. NULL for manual
    # CSV imports (which have an import_job_id instead).
    data_source_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    business = relationship("Business", back_populates="transactions")
