"""Testa que o sistema completa até 4 rotas via desvios por ponto intermediário."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from agroroute import service
from agroroute.api import app
from agroroute.providers import RawRoute

client = TestClient(app)
KEY = {"X-API-Key": "demo-mg-2026"}


class OneRouteProvider:
    """Devolve 1 rota principal e sabe gerar desvios distintos (route_via)."""
    def __init__(self):
        self.calls = 0

    async def routes(self, origin, dest, vehicle_id, max_alternatives, client):
        return [RawRoute("Principal", "mock",
                         [[origin[0], origin[1]], [dest[0], dest[1]]], 100.0, 90.0)]

    async def route_via(self, origin, waypoint, dest, vehicle_id, client):
        self.calls += 1
        dist = 100.0 + self.calls * 8  # distância distinta -> sobrevive ao dedup
        return RawRoute("Alternativa", "mock",
                        [[origin[0], origin[1]], [waypoint[0], waypoint[1]], [dest[0], dest[1]]],
                        dist, dist)


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch):
    monkeypatch.setattr(service, "provider_for_tenant", lambda t: OneRouteProvider())

    async def no_elev(points, client):
        return [None] * len(points)

    async def no_precip(lat, lon, client):
        return None

    monkeypatch.setattr(service, "fetch_elevations", no_elev)
    monkeypatch.setattr(service, "fetch_precip_7d_mm", no_precip)


def test_compute_returns_four_routes():
    job = {"origin_lat": -19.85, "origin_lon": -48.52,
           "dest_lat": -19.97, "dest_lon": -47.78, "vehicle_id": "rodotrem",
           "climate": "seco"}
    r = client.post("/v1/routes/compute", json=job, headers=KEY)
    assert r.status_code == 200
    opts = r.json()["options"]
    assert len(opts) == 4                          # 1 principal + 3 desvios
    assert opts[0].get("cost")                      # todas custeadas
    names = [o["name"] for o in opts]
    assert names[0] == "Principal"
    # distâncias distintas (rotas genuinamente diferentes)
    dists = sorted(o["distance_km"] for o in opts)
    assert len(set(dists)) == 4
