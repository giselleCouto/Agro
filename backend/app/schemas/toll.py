from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class TollPlazaCreate(BaseModel):
    client_id: Optional[int] = None
    name: str
    highway: Optional[str] = None
    km: Optional[float] = None
    latitude: float
    longitude: float
    cost_per_axle: float = 7.80
    bidirectional: bool = True


class TollPlazaResponse(BaseModel):
    id: int
    name: str
    highway: Optional[str]
    km: Optional[float]
    latitude: float
    longitude: float
    cost_per_axle: float
    bidirectional: bool
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True
