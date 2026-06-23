from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class RouteCalculateRequest(BaseModel):
    field_id: int
    plant_id: int
    vehicle_id: Optional[int] = None  # None = calcular para todos
    climate: str = "safra_mix"
    occupancy_pct: float = 100.0
    force_recalculate: bool = False


class RouteResponse(BaseModel):
    id: int
    field_id: int
    plant_id: int
    vehicle_id: int
    route_type: str
    distance_km: Optional[float]
    duration_min: Optional[float]
    elevation_gain_m: Optional[float]
    elevation_loss_m: Optional[float]
    avg_slope_pct: Optional[float]
    fuel_liters: Optional[float]
    fuel_cost: Optional[float]
    toll_count: int
    toll_cost: float
    total_cost: Optional[float]
    highway_mix: dict
    suitability_score: int
    trafficability_scores: dict
    passes_urban_zone: bool
    coordinates: Optional[list] = None
    elevation_profile: Optional[list] = None
    source: str
    calculated_at: datetime

    class Config:
        from_attributes = True


class RouteComparisonResponse(BaseModel):
    field_name: str
    farm_name: str
    plant_name: str
    distance_to_plant_km: float
    gps_route: Optional[RouteResponse] = None
    alternative_routes: list[RouteResponse] = []
    best_route: Optional[RouteResponse] = None
    economy_per_trip: Optional[float] = None
    economy_per_season: Optional[float] = None
    economy_pct: Optional[float] = None
