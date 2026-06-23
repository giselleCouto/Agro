"""
CanaRoute - Schemas Pydantic para API
"""
from .client import ClientCreate, ClientResponse, ClientList
from .plant import PlantCreate, PlantResponse
from .field import FieldCreate, FieldResponse, FieldBulkResponse
from .vehicle import VehicleCreate, VehicleResponse
from .toll import TollPlazaCreate, TollPlazaResponse
from .urban_zone import UrbanZoneCreate, UrbanZoneResponse
from .route import RouteResponse, RouteCalculateRequest, RouteComparisonResponse
from .economy import EconomyResponse, EconomySummary
from .onboarding import OnboardingRequest, OnboardingStatus
