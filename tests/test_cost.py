"""Testes do motor físico de custo."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agroroute import cost
from agroroute.models import (
    DEFAULT_FLEET,
    ClimateState,
    Segment,
    Surface,
    TollCrossing,
)


def flat_segment(km=1.0, surface=Surface.ASPHALT, slope=0.0):
    return Segment(
        lat0=-21.0, lon0=-48.0, lat1=-21.0, lon1=-48.0 + km / 100,
        dist_km=km, slope_pct=slope, surface=surface,
    )


def test_fuel_matches_sajb_formula_flat_dry_asphalt():
    """Plano, seco, asfalto: L = R0 * PBT * km (fórmula original do v3)."""
    truck = DEFAULT_FLEET["treminhao"]  # 20t + 35t = 55t cheio
    segs = [flat_segment(km=10.0)]
    bd = cost.compute_cost(
        segments=segs, tolls=[], vehicle=truck, occupancy=1.0,
        climate=ClimateState.SECO, climate_k=1.0, diesel_price=6.0,
        round_trip=False,
    )
    expected = 0.0030 * 55.0 * 10.0  # 1.65 L
    assert math.isclose(bd.fuel_liters, expected, rel_tol=1e-6)


def test_slope_penalty_and_clip():
    truck = DEFAULT_FLEET["treminhao"]
    seg_up = [flat_segment(km=10.0, slope=4.0)]
    seg_steep = [flat_segment(km=10.0, slope=12.0)]  # deve clipar em 6%
    bd_up = cost.compute_cost(seg_up, [], truck, 1.0, ClimateState.SECO, 1.0, 6.0, round_trip=False)
    bd_steep = cost.compute_cost(seg_steep, [], truck, 1.0, ClimateState.SECO, 1.0, 6.0, round_trip=False)
    assert math.isclose(bd_up.fuel_liters, (0.0030 + 0.0040 * 4) * 55 * 10, rel_tol=1e-6)
    assert math.isclose(bd_steep.fuel_liters, (0.0030 + 0.0040 * 6) * 55 * 10, rel_tol=1e-6)


def test_round_trip_reverses_slope_and_empties_truck():
    """Ida cheia subindo + volta vazia descendo: volta só paga R0 com tara."""
    truck = DEFAULT_FLEET["treminhao"]
    segs = [flat_segment(km=10.0, slope=4.0)]
    bd = cost.compute_cost(segs, [], truck, 1.0, ClimateState.SECO, 1.0, 6.0, round_trip=True)
    ida = (0.0030 + 0.0040 * 4) * 55 * 10
    volta = 0.0030 * 20 * 10  # descida clipada em 0, tara 20t
    assert math.isclose(bd.fuel_liters, ida + volta, rel_tol=1e-6)


def test_climate_hits_dirt_much_more_than_asphalt():
    """Enlameado (k=1.30): terra sofre integral, asfalto quase nada."""
    truck = DEFAULT_FLEET["treminhao"]
    dirt = [flat_segment(km=10.0, surface=Surface.DIRT)]
    asph = [flat_segment(km=10.0, surface=Surface.ASPHALT)]
    kwargs = dict(tolls=[], vehicle=truck, occupancy=1.0,
                  climate=ClimateState.ENLAMEADO, climate_k=1.30,
                  diesel_price=6.0, round_trip=False)
    bd_dirt = cost.compute_cost(dirt, **kwargs)
    bd_asph = cost.compute_cost(asph, **kwargs)
    assert math.isclose(bd_dirt.climate_k_applied, 1.30, rel_tol=1e-6)
    assert math.isclose(bd_asph.climate_k_applied, 1.045, rel_tol=1e-6)
    # terra também rola pior (mult 1.28)
    assert bd_dirt.fuel_liters > bd_asph.fuel_liters * 1.2


def test_toll_per_axle_with_raised_axles_when_empty():
    """Rodotrem 9 eixos, 2 suspensos vazio: ida 9 eixos, volta 7 eixos."""
    truck = DEFAULT_FLEET["rodotrem"]
    tolls = [TollCrossing(name="P1", lat=0, lon=0, tariff_per_axle=2.0)]
    bd = cost.compute_cost([flat_segment()], tolls, truck, 1.0,
                           ClimateState.SECO, 1.0, 6.0, round_trip=True)
    assert math.isclose(bd.toll_cost, 2.0 * 9 + 2.0 * 7, rel_tol=1e-6)


def test_maintenance_scales_with_surface_and_weight():
    truck = DEFAULT_FLEET["treminhao"]  # 1.10 R$/km ref 55t
    segs = [flat_segment(km=10.0, surface=Surface.DIRT)]
    bd = cost.compute_cost(segs, [], truck, 1.0, ClimateState.SECO, 1.0, 6.0, round_trip=False)
    expected = 1.10 * 1.60 * (55 / 55) * 10
    assert math.isclose(bd.maintenance_cost, expected, rel_tol=1e-6)


def test_auto_climate_classification_from_rain():
    assert cost.classify_climate(0.0) == ClimateState.SECO
    assert cost.classify_climate(20) == ClimateState.UMIDO
    assert cost.classify_climate(50) == ClimateState.MOLHADO
    assert cost.classify_climate(100) == ClimateState.ENLAMEADO
    assert cost.classify_climate(200) == ClimateState.SEVERO
    assert cost.classify_climate(None) == ClimateState.SAFRA_MIX
    assert cost.resolve_climate_k(ClimateState.AUTO, 200) == 1.50
