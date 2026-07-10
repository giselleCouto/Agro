"""Testes de frota, manutenção preditiva e dashboard."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute.api import app
from agroroute.fleet import predict_maintenance

client = TestClient(app)
DEMO = {"X-API-Key": "demo-mg-2026"}


def test_predict_maintenance_severities():
    v = {"tire_km": 76500, "tire_limit_km": 80000,     # ~96% -> critical
         "brake_km": 25000, "brake_limit_km": 50000,   # 50% -> medium
         "suspension_km": 12000, "suspension_limit_km": 120000,  # 10% -> low
         "engine_hours": 12000, "engine_limit_hours": 15000}     # 80% -> high
    preds = {p["component"]: p for p in predict_maintenance(v)}
    assert preds["tires"]["severity"] == "critical"
    assert preds["brakes"]["severity"] == "medium"
    assert preds["suspension"]["severity"] == "low"
    assert preds["engine"]["severity"] == "high"


def test_fleet_endpoint_seeded():
    r = client.get("/v1/fleet", headers=DEMO)
    assert r.status_code == 200
    body = r.json()
    assert len(body["vehicles"]) >= 10          # demo-mg semeado (frota de materialidade)
    assert body["summary"]["total"] == len(body["vehicles"])
    assert "severity_counts" in body["summary"]
    assert all("maintenance" in v for v in body["vehicles"])


def test_fleet_add_vehicle():
    before = len(client.get("/v1/fleet", headers=DEMO).json()["vehicles"])
    r = client.post("/v1/fleet", json={"plate": "MG-TEST-9", "type": "rodotrem",
                                       "display_name": "Teste", "tire_km": 10000}, headers=DEMO)
    assert r.status_code == 200
    after = len(client.get("/v1/fleet", headers=DEMO).json()["vehicles"])
    assert after == before + 1


def test_fleet_add_duplicate_plate_conflict():
    v = {"plate": "DUP-PLATE-1", "type": "treminhao"}
    assert client.post("/v1/fleet", json=v, headers=DEMO).status_code == 200
    r = client.post("/v1/fleet", json=v, headers=DEMO)   # placa repetida
    assert r.status_code == 409


def test_dashboard_endpoint():
    r = client.get("/v1/dashboard", headers=DEMO)
    assert r.status_code == 200
    d = r.json()
    assert d["tenant"]["is_demo"] is True
    assert "fleet" in d and "routes" in d and "billing" in d
    assert d["billing"]["plan_id"] == "demo"


def test_fleet_requires_auth():
    assert client.get("/v1/fleet").status_code in (401, 422)
