from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime, date


VALID_ADJUSTMENT_TYPES = [
    "DELAY_DEPOSIT", "FEE_CORRECTION", "AUTOREFUND_OFFSET",
    "DUPLICATE_PAYMENT", "BANK_ERROR", "ACQUIRER_ERROR",
    "MANUAL_BITSO", "OTHER",
]

VALID_DIRECTIONS = ["ADD", "SUBTRACT", "OVERRIDE"]
VALID_AFFECTS = ["expected", "received", "delta"]


class AdjustmentCreate(BaseModel):
    adjustment_type: str
    direction: str
    amount: float
    currency: str = "MXN"
    affects: str
    conciliation_type: Optional[str] = None
    merchant_name: Optional[str] = None
    adjustment_date: Optional[date] = None
    description: str
    evidence_url: Optional[str] = None

    @field_validator("adjustment_type")
    @classmethod
    def validate_type(cls, v):
        if v not in VALID_ADJUSTMENT_TYPES:
            raise ValueError(f"adjustment_type must be one of {VALID_ADJUSTMENT_TYPES}")
        return v

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, v):
        if v not in VALID_DIRECTIONS:
            raise ValueError(f"direction must be one of {VALID_DIRECTIONS}")
        return v

    @field_validator("affects")
    @classmethod
    def validate_affects(cls, v):
        if v not in VALID_AFFECTS:
            raise ValueError(f"affects must be one of {VALID_AFFECTS}")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v):
        if len(v.strip()) < 10:
            raise ValueError("description must be at least 10 characters")
        return v


class AdjustmentReview(BaseModel):
    review_notes: Optional[str] = None


class AdjustmentOut(BaseModel):
    id: int
    process_id: int
    adjustment_type: str
    direction: str
    amount: float
    currency: str
    affects: str
    conciliation_type: Optional[str] = None
    merchant_name: Optional[str] = None
    adjustment_date: Optional[date] = None
    description: str
    evidence_url: Optional[str] = None
    created_by: int
    created_at: datetime
    status: str
    reviewed_by: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    class Config:
        from_attributes = True
