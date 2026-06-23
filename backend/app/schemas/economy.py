from pydantic import BaseModel
from typing import Optional


class EconomyResponse(BaseModel):
    field_id: int
    field_name: str
    farm_name: str
    vehicle_name: str
    gps_cost: float
    alt_cost: float
    saving_per_trip: float
    saving_per_season: float
    saving_pct: float
    climate: str


class EconomySummary(BaseModel):
    client_id: int
    client_name: str
    total_fields: int
    fields_with_economy: int
    fields_without_economy: int
    total_saving_per_season: float
    avg_saving_pct: float
    best_field: Optional[str] = None
    best_saving: Optional[float] = None
