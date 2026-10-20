"""transaction dedup columns for sync

Revision ID: 0003_sync_dedup_columns
Revises: 0002_data_sources
Create Date: 2026-10-20 00:00:01.000000

Adds two columns to ``transactions`` used by the sync service for
incremental imports:

- ``source_row_hash`` — a SHA-256 over the canonical field tuple.
- ``data_source_id`` — FK back to ``data_sources`` (SET NULL on
  cascade so deleting a source keeps the row).

Plain ``add_column`` / ``create_index`` operations on an existing
SQLite table work without batch mode for additive changes.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_sync_dedup_columns"
down_revision = "0002_data_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("source_row_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("data_source_id", sa.String(length=36), nullable=True),
    )
    # Note: SQLite + Alembic reject ALTER TABLE ADD CONSTRAINT for FKs.
    # The FK constraint is registered in SQLAlchemy metadata; a future
    # migration to Postgres will materialise the FK via raw SQL.
    op.create_index(
        "ix_transactions_data_source_id", "transactions", ["data_source_id"],
    )
    op.create_index(
        "uq_transactions_business_source_row_hash",
        "transactions",
        ["business_id", "source_row_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_transactions_business_source_row_hash", table_name="transactions")
    op.drop_index("ix_transactions_data_source_id", table_name="transactions")
    op.drop_column("transactions", "data_source_id")
    op.drop_column("transactions", "source_row_hash")