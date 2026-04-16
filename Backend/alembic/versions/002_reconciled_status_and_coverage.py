"""Add RECONCILED status, coverage tracking, and TrueBook v2 core tables

Revision ID: 002
Revises: 001
Create Date: 2026-04-15
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── accounting_processes: add reconciliation columns ────────────────
    op.add_column("accounting_processes",
                  sa.Column("reconciled_by", sa.Integer(),
                            sa.ForeignKey("users.id"), nullable=True))
    op.add_column("accounting_processes",
                  sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("accounting_processes",
                  sa.Column("coverage_pct", sa.Numeric(5, 2), nullable=True))

    # ── banregio_movement_classifications ───────────────────────────────
    op.create_table(
        "banregio_movement_classifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(),
                  sa.ForeignKey("accounting_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("movement_index", sa.Integer(), nullable=False),
        sa.Column("movement_date", sa.String(), nullable=True),
        sa.Column("movement_description", sa.Text(), nullable=True),
        sa.Column("movement_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("movement_type", sa.String(), nullable=True),
        sa.Column("classification", sa.String(), nullable=False),
        sa.Column("acquirer", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("classified_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("classification_method", sa.String(), default="manual"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.UniqueConstraint("process_id", "movement_index",
                            name="uq_classification_process_movement"),
    )
    op.create_index("ix_bmc_process_id", "banregio_movement_classifications",
                    ["process_id"])
    op.create_index("ix_bmc_classification", "banregio_movement_classifications",
                    ["classification"])

    # ── run_adjustments ────────────────────────────────────────────────
    op.create_table(
        "run_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(),
                  sa.ForeignKey("accounting_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("adjustment_type", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(3), default="MXN"),
        sa.Column("affects", sa.String(), nullable=False),
        sa.Column("conciliation_type", sa.String(), nullable=True),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("adjustment_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_url", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("status", sa.String(), default="pending"),
        sa.Column("reviewed_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_adj_process_id", "run_adjustments", ["process_id"])
    op.create_index("ix_adj_status", "run_adjustments", ["status"])

    # ── run_alerts ─────────────────────────────────────────────────────
    op.create_table(
        "run_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(),
                  sa.ForeignKey("accounting_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("alert_level", sa.String(), nullable=False),
        sa.Column("alert_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", postgresql.JSON(), nullable=True),
        sa.Column("is_acknowledged", sa.Boolean(), default=False),
        sa.Column("acknowledged_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_alert_process_id", "run_alerts", ["process_id"])
    op.create_index("ix_alert_level", "run_alerts", ["alert_level"])

    # ── reconciliation_config ──────────────────────────────────────────
    op.create_table(
        "reconciliation_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("config_key", sa.String(), unique=True, nullable=False),
        sa.Column("config_value", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("updated_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    # Seed default config values
    op.execute("""
        INSERT INTO reconciliation_config (config_key, config_value, description) VALUES
        ('conciliation_tolerance', '0.01', 'MXN. Tolerancia para matching en conciliaciones (default 1 centavo)'),
        ('banregio_warn_threshold_amount', '500.00', 'MXN. Delta que activa WARNING'),
        ('banregio_warn_threshold_pct', '0.5', '%. Porcentaje de delta vs expected total'),
        ('banregio_critical_coverage_pct', '95', '%. Cobertura mínima antes de CRITICAL'),
        ('bitso_match_tolerance_amount', '1.00', 'MXN. Tolerancia de monto en cruce Bitso'),
        ('bitso_match_window_days', '3', 'Días de ventana para cruce de fecha Bitso'),
        ('oxxo_delay_suppress_days', '3', 'Días de delay OXXO donde se suprime alerta')
    """)

    # ── bitso tables ──────────────────────────────────────────────────
    op.create_table(
        "bitso_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(),
                  sa.ForeignKey("accounting_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("file_id", sa.Integer(),
                  sa.ForeignKey("uploaded_files.id"), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("total_amount", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw_payload", postgresql.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )

    op.create_table(
        "bitso_report_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_id", sa.Integer(),
                  sa.ForeignKey("bitso_reports.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("line_index", sa.Integer(), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=True),
        sa.Column("txn_id", sa.String(), nullable=True),
        sa.Column("merchant_name", sa.String(), nullable=True),
        sa.Column("currency", sa.String(10), default="MXN"),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("fee_amount", sa.Numeric(14, 2), default=0),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("raw_row", postgresql.JSON(), nullable=True),
    )

    op.create_table(
        "bitso_banregio_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("process_id", sa.Integer(),
                  sa.ForeignKey("accounting_processes.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("bitso_line_id", sa.Integer(),
                  sa.ForeignKey("bitso_report_lines.id"), nullable=False),
        sa.Column("banregio_movement_index", sa.Integer(), nullable=False),
        sa.Column("bitso_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("banregio_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("delta", sa.Numeric(14, 2), nullable=True),
        sa.Column("match_method", sa.String(), nullable=False),
        sa.Column("matched_by", sa.Integer(),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("bitso_line_id", "process_id",
                            name="uq_bitso_line_process"),
        sa.UniqueConstraint("banregio_movement_index", "process_id",
                            name="uq_banregio_mov_process"),
    )


def downgrade() -> None:
    op.drop_table("bitso_banregio_matches")
    op.drop_table("bitso_report_lines")
    op.drop_table("bitso_reports")
    op.drop_table("reconciliation_config")
    op.drop_table("run_alerts")
    op.drop_table("run_adjustments")
    op.drop_table("banregio_movement_classifications")
    op.drop_column("accounting_processes", "coverage_pct")
    op.drop_column("accounting_processes", "reconciled_at")
    op.drop_column("accounting_processes", "reconciled_by")
