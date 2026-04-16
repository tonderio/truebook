from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric, Date,
)
from sqlalchemy.sql import func
from app.database import Base


class RunAdjustment(Base):
    __tablename__ = "run_adjustments"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("accounting_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Adjustment type codes (from reconciliation spec §3.1):
    #   DELAY_DEPOSIT, FEE_CORRECTION, AUTOREFUND_OFFSET,
    #   DUPLICATE_PAYMENT, BANK_ERROR, ACQUIRER_ERROR,
    #   MANUAL_BITSO, OTHER
    adjustment_type = Column(String, nullable=False)
    direction = Column(String, nullable=False)       # ADD | SUBTRACT | OVERRIDE
    amount = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(3), default="MXN")
    affects = Column(String, nullable=False)          # expected | received | delta
    conciliation_type = Column(String, nullable=True)  # fees | kushki_daily | kushki_vs_banregio
    merchant_name = Column(String, nullable=True)
    adjustment_date = Column(Date, nullable=True)
    description = Column(Text, nullable=False)        # min 10 chars enforced at API level
    evidence_url = Column(Text, nullable=True)

    # Creator
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Two-eye approval workflow
    status = Column(String, default="pending")  # pending | approved | rejected
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(Text, nullable=True)

    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
