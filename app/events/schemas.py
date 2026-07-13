from pydantic import BaseModel, Field
from datetime import datetime
from typing import Dict, Any, Optional

class EventCreate(BaseModel):
    event_type: str = Field(..., min_length=2, max_length=50, examples=["click", "pageview", "purchase"])
    payload: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary event payload data")

class EventOut(BaseModel):
    id: int
    event_type: str
    user_id: Optional[int] = None
    timestamp: datetime
    payload: Dict[str, Any]

    class Config:
        from_attributes = True

class AnalyticsSummary(BaseModel):
    total_events: int
    event_types: Dict[str, int]
    active_users_last_hour: int
    cached_at: datetime
    system_metrics: Dict[str, Any] = Field(default_factory=dict)

