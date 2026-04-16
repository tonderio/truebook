from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric, Date,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from app.database import Base


class BitsoReport(Base):
    __tablename__ = "bitso_reports"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("accounting_processes.id", ondelete="CASCADE"),
        nullable=False,
    )
    file_id = Column(Integer, ForeignKey("uploaded_files.id"), nullable=True)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    total_rows = Column(Integer, nullable=True)
    total_amount = Column(Numeric(18, 6), nullable=True)
    raw_payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class BitsoReportLine(Base):
    __tablename__ = "bitso_report_lines"

    id = Column(Integer, primary_key=True, index=True)
    report_id = Column(
        Integer,
        ForeignKey("bitso_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_index = Column(Integer, nullable=False)
    txn_date = Column(Date, nullable=True)
    txn_id = Column(String, nullable=True)
    merchant_name = Column(String, nullable=True)
    currency = Column(String(10), default="MXN")
    gross_amount = Column(Numeric(14, 2), nullable=True)
    fee_amount = Column(Numeric(14, 2), default=0)
    net_amount = Column(Numeric(14, 2), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String, nullable=True)
    raw_row = Column(JSON, nullable=True)


class BitsoBanregioMatch(Base):
    __tablename__ = "bitso_banregio_matches"
    __table_args__ = (
        UniqueConstraint("bitso_line_id", "process_id",
                         name="uq_bitso_line_process"),
        UniqueConstraint("banregio_movement_index", "process_id",
                         name="uq_banregio_mov_process"),
    )

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("accounting_processes.id", ondelete="CASCADE"),
        nullable=False,
    )
    bitso_line_id = Column(
        Integer,
        ForeignKey("bitso_report_lines.id"),
        nullable=False,
    )
    banregio_movement_index = Column(Integer, nullable=False)
    bitso_amount = Column(Numeric(14, 2), nullable=False)
    banregio_amount = Column(Numeric(14, 2), nullable=False)
    delta = Column(Numeric(14, 2), nullable=True)
    match_method = Column(String, nullable=False)  # 'auto' | 'manual'
    matched_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    matched_at = Column(DateTime(timezone=True), server_default=func.now())
    notes = Column(Text, nullable=True)
