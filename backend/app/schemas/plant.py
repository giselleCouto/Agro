from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class PlantCreate(BaseModel):
    client_id: int
    name: str
    code: Optional[str] = None
    latitude: float
    longitude: float
    capacity_tons_day: Optional[float] = None


class PlantResponse(BaseModel):
    id: int
    client_id: int
    name: str
    code: Optional[str]
    latitude: float
    longitude: float
    capacity_tons_day: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True
