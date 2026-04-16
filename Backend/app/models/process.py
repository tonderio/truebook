from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, JSON, Numeric
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class AccountingProcess(Base):
    __tablename__ = "accounting_processes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)
    acquirers = Column(JSON, default=["OXXOPay", "Bitso", "Kushki", "STP"])
    status = Column(String, default="pending")
    # pending | running | completed | reconciled | failed
    current_stage = Column(String, nullable=True)
    progress = Column(Integer, default=0)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    error_message = Column(Text, nullable=True)

    # Reconciliation tracking (TrueBook v2)
    reconciled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    reconciled_at = Column(DateTime(timezone=True), nullable=True)
    coverage_pct = Column(Numeric(5, 2), nullable=True)

    logs = relationship("ProcessLog", back_populates="process", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="process", cascade="all, delete-orphan")


class ProcessLog(Base):
    __tablename__ = "process_logs"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(Integer, ForeignKey("accounting_processes.id", ondelete="CASCADE"))
    stage = Column(String, nullable=False)
    level = Column(String, default="info")  # info | warning | error
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    process = relationship("AccountingProcess", back_populates="logs")
