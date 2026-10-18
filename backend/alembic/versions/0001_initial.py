"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2025-01-01 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=40), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("fiscal_year_start_month", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="en-US"),
        sa.Column("min_cash_reserve", sa.Numeric(20, 4), nullable=False, server_default="0"),
        sa.Column("target_operating_margin", sa.Numeric(6, 4), nullable=False, server_default="0.10"),
        sa.Column("max_unsold_inventory_exposure_pct", sa.Numeric(6, 4), nullable=False, server_default="0.20"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tx_date", sa.Date(), nullable=False),
        sa.Column("cash_flow_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("amount", sa.Numeric(20, 4), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False, server_default="USD"),
        sa.Column("direction", sa.String(length=16), nullable=False),  # inflow|outflow
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=True),  # paid|pending|partial
        sa.Column("customer_or_supplier", sa.String(length=200), nullable=True),
        sa.Column("source_file", sa.String(length=500), nullable=True),
        sa.Column("source_sheet", sa.String(length=200), nullable=True),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("import_job_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_transactions_business_date", "transactions", ["business_id", "tx_date"])

    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("encoding", sa.String(length=32), nullable=True),
        sa.Column("sheet_name", sa.String(length=200), nullable=True),
        sa.Column("column_mapping", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("row_count_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count_imported", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("row_count_rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validation_issues", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="committed"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("industry", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "scenario_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("scenario_id", sa.String(length=36), sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("inputs_json", sa.Text(), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=False, server_default="0.1.0"),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("calculation_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scenario_id", "version_number", name="uq_scenario_version"),
    )

    op.create_table(
        "decision_reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("business_id", sa.String(length=36), sa.ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scenario_version_id", sa.String(length=36), sa.ForeignKey("scenario_versions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("question", sa.String(length=500), nullable=False),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("overall_status", sa.String(length=32), nullable=False),
        sa.Column("laya_status", sa.String(length=32), nullable=False, server_default="not_used"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "llm_explanations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("decision_report_id", sa.String(length=36), sa.ForeignKey("decision_reports.id", ondelete="CASCADE"), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("llm_explanations")
    op.drop_table("decision_reports")
    op.drop_table("scenario_versions")
    op.drop_table("scenarios")
    op.drop_table("import_jobs")
    op.drop_table("transactions")
    op.drop_table("businesses")
