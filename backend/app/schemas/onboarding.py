from pydantic import BaseModel
from typing import Optional


class OnboardingRequest(BaseModel):
    client_name: str
    client_slug: str
    state: str = "SP"
    plant_name: str
    plant_latitude: float
    plant_longitude: float
    plant_capacity: Optional[float] = None
    # Shapefile será enviado como upload separado


class OnboardingStatus(BaseModel):
    client_id: int
    status: str  # pending, processing, completed, error
    steps_completed: list[str] = []
    steps_pending: list[str] = []
    fields_imported: int = 0
    routes_calculated: int = 0
    urban_zones_detected: int = 0
    toll_plazas_detected: int = 0
    message: str = ""
