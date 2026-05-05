from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ProcessCreate(BaseModel):
    name: str
    period_year: int
    period_month: int
    bank_account: str = "Banregio"
    acquirers: Optional[List[str]] = ["OXXOPay", "Bitso", "Kushki", "STP"]


class ProcessOut(BaseModel):
    id: int
    name: str
    period_year: int
    period_month: int
    bank_account: Optional[str] = "Banregio"
    acquirers: Optional[List[str]]
    status: str
    current_stage: Optional[str]
    progress: int
    created_by: Optional[int]
    created_at: datetime
    updated_at: Optional[datetime]
    error_message: Optional[str]
    reconciled_by: Optional[int] = None
    reconciled_at: Optional[datetime] = None
    coverage_pct: Optional[float] = None

    # True if a file with file_type='fees' has been uploaded to this
    # process. Drives the FEES-pending banner / Contabilidad list badge.
    # Computed by the list / get endpoints, not stored on the model.
    has_fees_file: bool = False

    class Config:
        from_attributes = True


class ProcessLogOut(BaseModel):
    id: int
    stage: str
    level: str
    message: str
    created_at: datetime

    class Config:
        from_attributes = True


class ProcessProgress(BaseModel):
    process_id: int
    status: str
    current_stage: Optional[str]
    progress: int
    logs: List[ProcessLogOut]
