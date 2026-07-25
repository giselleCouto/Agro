"""Tipos de domínio do Despaxa Agro."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Superfície e clima
# ---------------------------------------------------------------------------

class Surface(str, Enum):
    ASPHALT = "asphalt"        # asfalto
    CONCRETE = "concrete"      # concreto
    GRAVEL = "gravel"          # cascalho
    DIRT = "dirt"              # terra
    SAND = "sand"              # areia
    UNKNOWN = "unknown"


class ClimateState(str, Enum):
    """Estados climáticos herdados do modelo SAJB v3."""
    SECO = "seco"              # k = 1.00
    UMIDO = "umido"            # k = 1.08
    MOLHADO = "molhado"        # k = 1.15
    ENLAMEADO = "enlameado"    # k = 1.30
    SEVERO = "severo"          # k = 1.50
    SAFRA_MIX = "safra_mix"    # mix 50/30/15/5 -> k ~= 1.0775
    AUTO = "auto"              # deriva do Open-Meteo (chuva acumulada real)


CLIMATE_K: dict[ClimateState, float] = {
    ClimateState.SECO: 1.00,
    ClimateState.UMIDO: 1.08,
    ClimateState.MOLHADO: 1.15,
    ClimateState.ENLAMEADO: 1.30,
    ClimateState.SEVERO: 1.50,
    ClimateState.SAFRA_MIX: 1.0775,
}

# Sensibilidade da superfície ao clima: chuva quase não afeta asfalto,
# mas transforma estrada de terra em lama (fator integral).
CLIMATE_SENSITIVITY: dict[Surface, float] = {
    Surface.ASPHALT: 0.15,
    Surface.CONCRETE: 0.12,
    Surface.GRAVEL: 0.70,
    Surface.DIRT: 1.00,
    Surface.SAND: 0.90,
    Surface.UNKNOWN: 0.40,
}

# Resistência ao rolamento relativa ao asfalto (multiplicador de consumo).
ROLLING_MULT: dict[Surface, float] = {
    Surface.ASPHALT: 1.00,
    Surface.CONCRETE: 0.98,
    Surface.GRAVEL: 1.18,
    Surface.DIRT: 1.28,
    Surface.SAND: 1.50,
    Surface.UNKNOWN: 1.05,
}

# Desgaste de manutenção relativo ao asfalto (pneus, suspensão, freios).
MAINTENANCE_MULT: dict[Surface, float] = {
    Surface.ASPHALT: 1.00,
    Surface.CONCRETE: 1.00,
    Surface.GRAVEL: 1.35,
    Surface.DIRT: 1.60,
    Surface.SAND: 1.80,
    Surface.UNKNOWN: 1.10,
}


# ---------------------------------------------------------------------------
# Veículos (CVCs canavieiros)
# ---------------------------------------------------------------------------

class VehicleSpec(BaseModel):
    id: str
    name: str
    tare_t: float                  # peso vazio (t)
    payload_t: float               # carga útil máxima (t)
    axles: int                     # eixos totais
    axles_raised_empty: int = 0    # eixos suspensos quando vazio (pedágio menor)
    length_m: float = 25.0
    width_m: float = 2.6
    height_m: float = 4.4
    maintenance_rs_km: float = 1.20   # R$/km em asfalto, PBT cheio
    requires_aet: bool = True         # exige Autorização Especial de Trânsito

    @property
    def pbt_t(self) -> float:
        return self.tare_t + self.payload_t


DEFAULT_FLEET: dict[str, VehicleSpec] = {
    "treminhao": VehicleSpec(
        id="treminhao", name="Treminhão", tare_t=20.0, payload_t=35.0,
        axles=7, axles_raised_empty=1, length_m=25.0,
        maintenance_rs_km=1.10,
    ),
    "rodotrem": VehicleSpec(
        id="rodotrem", name="Rodotrem", tare_t=24.0, payload_t=46.0,
        axles=9, axles_raised_empty=2, length_m=30.0,
        maintenance_rs_km=1.35,
    ),
    "pentatrem": VehicleSpec(
        id="pentatrem", name="Pentatrem", tare_t=30.0, payload_t=60.0,
        axles=10, axles_raised_empty=2, length_m=36.0,
        maintenance_rs_km=1.60,
    ),
}


# ---------------------------------------------------------------------------
# Geometria enriquecida
# ---------------------------------------------------------------------------

class Segment(BaseModel):
    """Trecho elementar da rota (entre dois pontos amostrados)."""
    lat0: float
    lon0: float
    lat1: float
    lon1: float
    dist_km: float
    slope_pct: float = 0.0         # rampa média (+subida / -descida), sentido ida
    surface: Surface = Surface.UNKNOWN
    is_private: bool = False       # estrada particular (sem pedágio, manutenção própria)
    in_urban_zone: Optional[str] = None  # nome da cidade se dentro de zona restrita


class TollCrossing(BaseModel):
    name: str
    lat: float
    lon: float
    tariff_per_axle: float         # R$ por eixo (padrão ANTT para comerciais)


class AvoidZone(BaseModel):
    """Zona urbana/restrita: círculo (MVP) — polígonos entram via GeoJSON futuro."""
    name: str
    lat: float
    lon: float
    radius_km: float
    applies_to: list[str] = Field(default_factory=list)  # vazio = todos os veículos


class TollPlaza(BaseModel):
    name: str
    lat: float
    lon: float
    tariff_per_axle: float
    highway: str = ""


# ---------------------------------------------------------------------------
# Requisições / respostas
# ---------------------------------------------------------------------------

class RouteJob(BaseModel):
    """Um par origem-destino a calcular (ex.: talhão -> usina)."""
    job_id: str = "job-1"
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float
    vehicle_id: str = "treminhao"
    occupancy: float = Field(1.0, ge=0.0, le=1.0)  # fração da carga na ida
    round_trip: bool = True                        # ida carregado + volta vazio
    climate: ClimateState = ClimateState.AUTO
    max_alternatives: int = Field(4, ge=1, le=6)


class BatchRouteRequest(BaseModel):
    jobs: list[RouteJob]


class OptimizePoint(BaseModel):
    name: Optional[str] = None
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    supply: Optional[float] = Field(default=None, ge=0)   # oferta (origem), t
    demand: Optional[float] = Field(default=None, ge=0)   # demanda (destino), t


class OptimizeRequest(BaseModel):
    vehicle_id: str = "treminhao"
    origins: list[OptimizePoint] = Field(min_length=1)
    destinations: list[OptimizePoint] = Field(min_length=1)


class CostBreakdown(BaseModel):
    fuel_liters: float
    fuel_cost: float
    toll_cost: float
    maintenance_cost: float
    total_cost: float
    diesel_price: float
    climate_state: ClimateState
    climate_k_applied: float       # k médio efetivamente aplicado (ponderado por superfície)


class RouteOption(BaseModel):
    name: str
    provider: str
    distance_km: float
    duration_min: float
    geometry: list[list[float]]    # [[lat, lon], ...] — traçado real completo
    ascent_m: float = 0.0
    descent_m: float = 0.0
    elev_profile: list[list[float]] = Field(default_factory=list)  # [[km, m], ...] p/ gráfico
    surfaces_km: dict[str, float] = Field(default_factory=dict)
    tolls: list[TollCrossing] = Field(default_factory=list)
    urban_violations: list[str] = Field(default_factory=list)  # cidades atravessadas
    is_safe: bool = True           # sem violação urbana / restrição do veículo
    cost: Optional[CostBreakdown] = None


class RouteJobResult(BaseModel):
    job_id: str
    vehicle_id: str
    options: list[RouteOption]     # ordenadas por custo total (melhor primeiro)
    best_option: Optional[str] = None
    savings_vs_worst: float = 0.0  # R$ economizados escolhendo a melhor
    error: Optional[str] = None


class BatchRouteResponse(BaseModel):
    tenant_id: str
    results: list[RouteJobResult]


# ---------------------------------------------------------------------------
# Tenant
# ---------------------------------------------------------------------------

class TenantConfig(BaseModel):
    tenant_id: str
    name: str
    api_key: str
    diesel_price: float = 6.00
    osrm_base_url: str = "https://router.project-osrm.org"
    graphhopper_url: Optional[str] = None   # self-hosted com perfil truck (recomendado)
    graphhopper_key: Optional[str] = None
    avoid_zones: list[AvoidZone] = Field(default_factory=list)
    toll_plazas: list[TollPlaza] = Field(default_factory=list)
    fleet: dict[str, VehicleSpec] = Field(default_factory=dict)  # sobrescreve DEFAULT_FLEET
    private_road_data: Optional[str] = None  # caminho de GeoJSON com vias particulares

    def vehicle(self, vehicle_id: str) -> VehicleSpec:
        if vehicle_id in self.fleet:
            return self.fleet[vehicle_id]
        if vehicle_id in DEFAULT_FLEET:
            return DEFAULT_FLEET[vehicle_id]
        raise KeyError(f"veículo desconhecido: {vehicle_id}")
