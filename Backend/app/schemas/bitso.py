from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import date, datetime


class BitsoUploadResponse(BaseModel):
    report_id: int
    total_rows: int
    total_amount: float
    period_start: Optional[date] = None
    period_end: Optional[date] = None


class BitsoReportLineOut(BaseModel):
    id: int
    line_index: int
    txn_date: Optional[date] = None
    txn_id: Optional[str] = None
    merchant_name: Optional[str] = None
    gross_amount: Optional[float] = None
    fee_amount: Optional[float] = None
    net_amount: Optional[float] = None
    description: Optional[str] = None
    is_matched: bool = False

    class Config:
        from_attributes = True


class BitsoCandidate(BaseModel):
    banregio_movement_index: int
    movement_date: Optional[str] = None
    movement_description: Optional[str] = None
    movement_amount: float
    delta: float
    date_distance_days: int
    confidence: str  # 'high' | 'medium' | 'low'


class BitsoMatchRequest(BaseModel):
    bitso_line_id: int
    banregio_movement_index: int
    notes: Optional[str] = None


class BitsoMatchOut(BaseModel):
    id: int
    bitso_line_id: int
    banregio_movement_index: int
    bitso_amount: float
    banregio_amount: float
    delta: float
    match_method: str
    matched_by: Optional[int] = None
    matched_at: Optional[datetime] = None
    notes: Optional[str] = None
    suggested_adjustment: Optional[dict] = None

    class Config:
        from_attributes = True


class BitsoSummary(BaseModel):
    total_lines: int
    matched: int
    unmatched: int
    total_bitso_amount: float
    total_banregio_matched: float
    total_delta: float
