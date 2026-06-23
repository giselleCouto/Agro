from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UrbanZoneCreate(BaseModel):
    client_id: Optional[int] = None
    name: str
    latitude: float
    longitude: float
    radius_m: float = 2000
    restriction_level: str = "blocked"


class UrbanZoneResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: float
    restriction_level: str
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True
