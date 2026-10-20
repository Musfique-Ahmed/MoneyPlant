"""data sources and sync runs

Revision ID: 0002_data_sources
Revises: 0001_initial
Create Date: 2026-10-20 00:00:00.000000

Adds two new tables for the "data sources" feature:

- ``data_sources``: persistent configuration for an external source of
  transactions (one of ``file`` or ``sql``). Holds the column mapping,
  the incremental watermark column, the schedule and the (env-referenced)
  secret pointer. Credentials are never stored here.

- ``sync_runs``: one row per sync attempt — when it started, when it
  finished, how many rows were read / added / skipped-as-duplicate /
  rejected-as-invalid, and a short error summary if the run failed.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_data_sources"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("column_mapping", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("incremental_key", sa.String(length=64), nullable=True),
        sa.Column("incremental_value", sa.String(length=200), nullable=True),
        sa.Column("file_content_sha256", sa.String(length=64), nullable=True),
        sa.Column("schedule", sa.String(length=16), nullable=False, server_default="daily"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(length=16), nullable=False, server_default="never_run"),
        sa.Column("last_error_summary", sa.String(length=500), nullable=True),
        sa.Column("secret_ref", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_data_sources_business_id", "data_sources", ["business_id"])
    op.create_index("ix_data_sources_enabled", "data_sources", ["enabled"])

    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_id", sa.String(length=36), sa.ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("rows_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_skipped_duplicate", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rows_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_issues", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("error_summary", sa.String(length=500), nullable=True),
        sa.Column("trigger", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sync_runs_source_id", "sync_runs", ["source_id"])
    op.create_index("ix_sync_runs_started_at", "sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_runs_started_at", table_name="sync_runs")
    op.drop_index("ix_sync_runs_source_id", table_name="sync_runs")
    op.drop_table("sync_runs")

    op.drop_index("ix_data_sources_enabled", table_name="data_sources")
    op.drop_index("ix_data_sources_business_id", table_name="data_sources")
    op.drop_table("data_sources")
