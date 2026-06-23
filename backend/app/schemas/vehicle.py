from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class VehicleCreate(BaseModel):
    client_id: Optional[int] = None
    name: str
    slug: str
    pbt_tons: float
    axles: int
    length_m: float
    width_m: float
    min_road_class: str = "tertiary"
    caution_road_classes: list[str] = []
    blocked_road_classes: list[str] = []
    speed_by_road_class: dict = {}
    fuel_r0: float = 0.0030
    fuel_alpha: float = 0.0040


class VehicleResponse(BaseModel):
    id: int
    name: str
    slug: str
    pbt_tons: float
    axles: int
    length_m: float
    width_m: float
    min_road_class: str
    caution_road_classes: list[str]
    blocked_road_classes: list[str]
    speed_by_road_class: dict
    fuel_r0: float
    fuel_alpha: float
    created_at: datetime

    class Config:
        from_attributes = True
