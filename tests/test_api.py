"""Teste de integração da API com provider e fontes externas mockados (sem rede)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from agroroute import service
from agroroute.api import app
from agroroute.providers import RawRoute
from agroroute.models import Surface

client = TestClient(app)
KEY = {"X-API-Key": "sajb-dev-key-troque-em-producao"}


# Geometria sintética: passa exatamente pelo pedágio SP-322 (Guariba) e pela
# zona urbana de Guariba na "Alternativa 1".
ROUTE_SAFE = RawRoute(
    name="Principal", provider="mock",
    geometry=[[-21.3436, -48.3050], [-21.3280, -48.1850], [-21.3000, -48.1000]],
    distance_km=25.0, duration_min=30.0,
    elevations=[540.0, 580.0, 560.0],
    surface_by_point={0: Surface.ASPHALT, 1: Surface.GRAVEL},
)
ROUTE_URBAN = RawRoute(
    name="Alternativa 1", provider="mock",
    geometry=[[-21.3436, -48.3050], [-21.3570, -48.2290], [-21.3000, -48.1000]],
    distance_km=22.0, duration_min=26.0,
    elevations=[540.0, 550.0, 560.0],
)


class MockProvider:
    async def routes(self, origin, dest, vehicle_id, max_alternatives, client):
        return [ROUTE_SAFE, ROUTE_URBAN]


@pytest.fixture(autouse=True)
def mock_external(monkeypatch):
    monkeypatch.setattr(service, "provider_for_tenant", lambda t: MockProvider())

    async def fake_precip(lat, lon, client):
        return 150.0  # chuva forte -> clima severo

    monkeypatch.setattr(service, "fetch_precip_7d_mm", fake_precip)


def test_auth_required():
    r = client.post("/v1/routes/compute", json={})
    assert r.status_code in (401, 422)
    r = client.get("/v1/vehicles", headers={"X-API-Key": "chave-errada"})
    assert r.status_code == 401


def test_vehicles_lists_default_fleet():
    r = client.get("/v1/vehicles", headers=KEY)
    assert r.status_code == 200
    fleet = r.json()
    assert set(fleet) >= {"treminhao", "rodotrem", "pentatrem"}
    assert fleet["pentatrem"]["axles"] == 10


def test_compute_ranks_safe_route_first_and_prices_everything():
    job = {
        "job_id": "talhao-42",
        "origin_lat": -21.3436, "origin_lon": -48.3050,
        "dest_lat": -21.3000, "dest_lon": -48.1000,
        "vehicle_id": "rodotrem",
        "occupancy": 1.0,
        "round_trip": True,
        "climate": "auto",
    }
    r = client.post("/v1/routes/compute", json=job, headers=KEY)
    assert r.status_code == 200
    result = r.json()
    assert result["error"] is None
    opts = result["options"]
    assert len(opts) == 2

    # a rota mais curta viola a zona urbana de Guariba -> nunca vence
    best = opts[0]
    assert best["name"] == "Principal"
    assert best["is_safe"] is True
    assert opts[1]["urban_violations"] == ["Guariba"]
    assert opts[1]["is_safe"] is False

    # pedágio por eixo: rodotrem 9 eixos ida (1.78*9) + 7 volta (1.78*7)
    assert len(best["tolls"]) == 1
    assert abs(best["cost"]["toll_cost"] - (1.78 * 9 + 1.78 * 7)) < 0.01

    # clima AUTO com 150 mm/7d -> severo
    assert best["cost"]["climate_state"] == "severo"
    assert best["cost"]["fuel_liters"] > 0
    assert best["cost"]["total_cost"] > best["cost"]["toll_cost"]

    # superfície veio do provider (asfalto + cascalho)
    assert "gravel" in best["surfaces_km"]


def test_batch_computes_multiple_jobs_concurrently():
    jobs = {
        "jobs": [
            {
                "job_id": f"talhao-{i}",
                "origin_lat": -21.34, "origin_lon": -48.30,
                "dest_lat": -21.30, "dest_lon": -48.10,
                "vehicle_id": "treminhao",
                "climate": "seco",
            }
            for i in range(5)
        ]
    }
    r = client.post("/v1/routes/batch", json=jobs, headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "sajb"
    assert len(body["results"]) == 5
    assert all(res["best_option"] for res in body["results"])
