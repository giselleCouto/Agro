"""Testes do custom model por requisição do GraphHopperProvider."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agroroute.models import AvoidZone, TenantConfig
from agroroute.providers import GraphHopperProvider, _circle_polygon


def make_tenant():
    return TenantConfig(
        tenant_id="t1", name="T1", api_key="k",
        graphhopper_url="http://localhost:8989",
        avoid_zones=[
            AvoidZone(name="Guariba", lat=-21.357, lon=-48.229, radius_km=2.0),
            AvoidZone(name="SoRodotrem", lat=-21.0, lon=-48.0, radius_km=1.0,
                      applies_to=["rodotrem"]),
        ],
    )


def test_custom_model_has_weight_rule_and_zone_areas():
    p = GraphHopperProvider("http://localhost:8989", tenant=make_tenant())
    cm = p._request_custom_model("treminhao")
    # PBT do treminhão = 55 t -> bloqueia vias com limite legal menor
    assert {"if": "max_weight < 55", "multiply_by": "0"} in cm["priority"]
    # zona 0 vale para todos; zona 1 só para rodotrem
    ids = [f["id"] for f in cm["areas"]["features"]]
    assert ids == ["zone_0"]
    assert {"if": "in_zone_0", "multiply_by": "0.02"} in cm["priority"]


def test_zone_applies_to_filters_by_vehicle():
    p = GraphHopperProvider("http://localhost:8989", tenant=make_tenant())
    cm = p._request_custom_model("rodotrem")
    ids = [f["id"] for f in cm["areas"]["features"]]
    assert set(ids) == {"zone_0", "zone_1"}


def test_circle_polygon_is_closed_ring():
    ring = _circle_polygon(-21.357, -48.229, 2.0)[0]
    assert ring[0] == ring[-1]
    assert len(ring) == 21
    # todos os pontos a ~2 km do centro (tolerância da projeção)
    from agroroute.geo import haversine_km
    for lon, lat in ring[:-1]:
        assert abs(haversine_km(-21.357, -48.229, lat, lon) - 2.0) < 0.1


def test_no_custom_model_without_tenant():
    p = GraphHopperProvider("http://localhost:8989")
    assert p._request_custom_model("treminhao") is None
