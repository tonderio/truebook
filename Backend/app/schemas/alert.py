from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime


class AlertOut(BaseModel):
    id: int
    process_id: int
    alert_level: str
    alert_type: str
    title: str
    message: str
    metadata_json: Optional[Any] = None
    is_acknowledged: bool
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ConfigOut(BaseModel):
    id: int
    config_key: str
    config_value: str
    description: Optional[str] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    config_value: str
