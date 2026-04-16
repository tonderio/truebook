from pydantic import BaseModel, Field
from typing import Optional, List


class WarrenSuggestionItem(BaseModel):
    movement_index: int = Field(ge=0)
    label: Optional[str] = None
    suggested_label: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = None


class ApplyWarrenRequest(BaseModel):
    suggestions: List[WarrenSuggestionItem]
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
