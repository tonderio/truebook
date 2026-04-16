from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ClassificationCreate(BaseModel):
    classification: str
    acquirer: Optional[str] = None
    notes: Optional[str] = None


class ClassificationOut(BaseModel):
    id: int
    process_id: int
    movement_index: int
    movement_date: Optional[str] = None
    movement_description: Optional[str] = None
    movement_amount: Optional[float] = None
    movement_type: Optional[str] = None
    classification: str
    acquirer: Optional[str] = None
    notes: Optional[str] = None
    classified_by: Optional[int] = None
    classification_method: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CoverageStats(BaseModel):
    total_movements: int
    classified: int
    unclassified: int
    ignored: int
    coverage_pct: float
    by_classification: dict  # {classification: count}


class BulkClassifyRequest(BaseModel):
    movement_indices: List[int]
    classification: str
    acquirer: Optional[str] = None
    notes: Optional[str] = None
