from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Numeric,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class BanregioMovementClassification(Base):
    __tablename__ = "banregio_movement_classifications"
    __table_args__ = (
        UniqueConstraint("process_id", "movement_index",
                         name="uq_classification_process_movement"),
    )

    id = Column(Integer, primary_key=True, index=True)
    process_id = Column(
        Integer,
        ForeignKey("accounting_processes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    movement_index = Column(Integer, nullable=False)
    movement_date = Column(String, nullable=True)
    movement_description = Column(Text, nullable=True)
    movement_amount = Column(Numeric(18, 6), nullable=True)
    movement_type = Column(String, nullable=True)  # 'cargo' | 'abono'
    classification = Column(String, nullable=False)
    # Valid classifications (12 categories from March 2026 labelling):
    # Acquirer deposits:
    #   'kushki_acquirer', 'bitso_acquirer', 'unlimit_acquirer',
    #   'pagsmile_acquirer', 'stp_acquirer'
    # Operational:
    #   'settlement_to_merchant', 'revenue', 'investment',
    #   'tax', 'bank_expense', 'currency_sale', 'transfer_between_accounts'
    # Manual:
    #   'ignored', 'other', 'unclassified'
    acquirer = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    classified_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    classification_method = Column(String, default="manual")  # 'auto' | 'manual'
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now())
