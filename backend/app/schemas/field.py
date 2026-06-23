from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class FieldCreate(BaseModel):
    client_id: int
    farm_name: Optional[str] = None
    code: Optional[str] = None
    name: Optional[str] = None
    area_ha: Optional[float] = None
    latitude: float
    longitude: float


class FieldResponse(BaseModel):
    id: int
    client_id: int
    farm_id: Optional[int]
    farm_name: Optional[str] = None
    code: Optional[str]
    name: Optional[str]
    area_ha: Optional[float]
    latitude: float
    longitude: float
    active: bool
    distance_to_plant_km: Optional[float] = None
    created_at: datetime

    class Config:
        from_attributes = True


class FieldBulkResponse(BaseModel):
    fields_created: int
    farms_created: int
    total_area_ha: float
    message: str
