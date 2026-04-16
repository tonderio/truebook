from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.sql import func
from app.database import Base


class RunAlert(Base):
    __tablename__ = "run_alerts"

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("accounting_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Alert levels from reconciliation spec §5.1:
    #   OK, INFO, WARNING, CRITICAL, UNCLASSIFIED,
    #   FALTANTE, SOBRANTE, BITSO_PENDING
    alert_level = Column(String, nullable=False, index=True)
    alert_type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(JSON, nullable=True)

    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ReconciliationConfig(Base):
    __tablename__ = "reconciliation_config"

    id = Column(Integer, primary_key=True, index=True)
    config_key = Column(String, unique=True, nullable=False)
    config_value = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
