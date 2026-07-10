"""Motor físico de custo — generalização do modelo SAJB v3.

Combustível por segmento e sentido:
    L = (R0 + alpha * max(0, slope%)) * mult_superficie * PBT * dKm * k_clima_seg

  - R0    = 0.0030 L/(km.t)      resistência base (rolamento + transmissão)
  - alpha = 0.0040 L/(km.t.%)    penalidade de rampa, clipada em 6%
  - PBT   = tara + carga*ocupação (ida) | tara (volta)
  - k_clima_seg = 1 + (k_clima - 1) * sensibilidade(superfície)
      chuva pesa pouco no asfalto e integralmente na terra (lama).

Pedágio: tarifa_por_eixo * eixos_cobrados; vazio com eixos suspensos paga menos.
Manutenção: R$/km base * desgaste(superfície) * fator_peso.
"""
from __future__ import annotations

from .models import (
    CLIMATE_K,
    CLIMATE_SENSITIVITY,
    MAINTENANCE_MULT,
    ROLLING_MULT,
    ClimateState,
    CostBreakdown,
    Segment,
    TollCrossing,
    VehicleSpec,
)

R0 = 0.0030          # L/(km.t)
ALPHA = 0.0040       # L/(km.t.%)
SLOPE_CLIP_PCT = 6.0
WEIGHT_MAINT_REF_T = 55.0  # treminhão cheio = referência do R$/km de manutenção


def _fuel_one_way(
    segments: list[Segment],
    pbt_t: float,
    k_climate: float,
    reverse: bool,
) -> tuple[float, float]:
    """Litros e k médio ponderado por km para um sentido.

    No sentido de volta a rampa inverte de sinal (descida vira subida).
    """
    liters = 0.0
    k_weighted = 0.0
    total_km = 0.0
    for seg in segments:
        slope = -seg.slope_pct if reverse else seg.slope_pct
        slope = min(max(slope, 0.0), SLOPE_CLIP_PCT)
        k_seg = 1.0 + (k_climate - 1.0) * CLIMATE_SENSITIVITY[seg.surface]
        rate = (R0 + ALPHA * slope) * ROLLING_MULT[seg.surface]
        liters += rate * pbt_t * seg.dist_km * k_seg
        k_weighted += k_seg * seg.dist_km
        total_km += seg.dist_km
    k_avg = k_weighted / total_km if total_km > 0 else 1.0
    return liters, k_avg


def _toll_cost(tolls: list[TollCrossing], axles_charged: int) -> float:
    return sum(t.tariff_per_axle * axles_charged for t in tolls)


def _maintenance_cost(
    segments: list[Segment], vehicle: VehicleSpec, pbt_t: float
) -> float:
    weight_factor = pbt_t / WEIGHT_MAINT_REF_T
    cost = 0.0
    for seg in segments:
        cost += (
            vehicle.maintenance_rs_km
            * MAINTENANCE_MULT[seg.surface]
            * weight_factor
            * seg.dist_km
        )
    return cost


def compute_cost(
    segments: list[Segment],
    tolls: list[TollCrossing],
    vehicle: VehicleSpec,
    occupancy: float,
    climate: ClimateState,
    climate_k: float,
    diesel_price: float,
    round_trip: bool = True,
) -> CostBreakdown:
    """Custo total da viagem (ida carregado; volta vazia se round_trip).

    `climate_k` já resolvido (para AUTO, o service deriva do Open-Meteo antes).
    """
    pbt_loaded = vehicle.tare_t + vehicle.payload_t * occupancy
    pbt_empty = vehicle.tare_t

    fuel_l, k_avg = _fuel_one_way(segments, pbt_loaded, climate_k, reverse=False)
    maint = _maintenance_cost(segments, vehicle, pbt_loaded)
    toll = _toll_cost(tolls, vehicle.axles)

    if round_trip:
        fuel_back, _ = _fuel_one_way(segments, pbt_empty, climate_k, reverse=True)
        fuel_l += fuel_back
        maint += _maintenance_cost(segments, vehicle, pbt_empty)
        axles_empty = max(2, vehicle.axles - vehicle.axles_raised_empty)
        toll += _toll_cost(tolls, axles_empty)

    fuel_cost = fuel_l * diesel_price
    return CostBreakdown(
        fuel_liters=round(fuel_l, 2),
        fuel_cost=round(fuel_cost, 2),
        toll_cost=round(toll, 2),
        maintenance_cost=round(maint, 2),
        total_cost=round(fuel_cost + toll + maint, 2),
        diesel_price=diesel_price,
        climate_state=climate,
        climate_k_applied=round(k_avg, 4),
    )


def resolve_climate_k(climate: ClimateState, precip_7d_mm: float | None = None) -> float:
    """Fator k do clima. Para AUTO, classifica pela chuva acumulada em 7 dias."""
    if climate != ClimateState.AUTO:
        return CLIMATE_K[climate]
    if precip_7d_mm is None:
        return CLIMATE_K[ClimateState.SAFRA_MIX]
    if precip_7d_mm < 5:
        return CLIMATE_K[ClimateState.SECO]
    if precip_7d_mm < 30:
        return CLIMATE_K[ClimateState.UMIDO]
    if precip_7d_mm < 70:
        return CLIMATE_K[ClimateState.MOLHADO]
    if precip_7d_mm < 120:
        return CLIMATE_K[ClimateState.ENLAMEADO]
    return CLIMATE_K[ClimateState.SEVERO]


def classify_climate(precip_7d_mm: float | None) -> ClimateState:
    if precip_7d_mm is None:
        return ClimateState.SAFRA_MIX
    if precip_7d_mm < 5:
        return ClimateState.SECO
    if precip_7d_mm < 30:
        return ClimateState.UMIDO
    if precip_7d_mm < 70:
        return ClimateState.MOLHADO
    if precip_7d_mm < 120:
        return ClimateState.ENLAMEADO
    return ClimateState.SEVERO
