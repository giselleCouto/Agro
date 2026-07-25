"""Trava da demonstração: só 5 rotas e recursos avançados bloqueados (403)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute.api import app
from agroroute.billing import PLANS

client = TestClient(app)
DEMO = {"X-API-Key": "demo-mg-2026"}   # tenant is_demo


def test_demo_quota_is_five():
    assert PLANS["demo"].routes_per_month == 5


def test_demo_start_creates_isolated_session():
    # cada novo usuário ganha sua própria demo (sandbox + cota próprios)
    k1 = client.post("/v1/demo/start").json()["api_key"]
    k2 = client.post("/v1/demo/start").json()["api_key"]
    assert k1 and k2 and k1 != k2

    h1 = {"X-API-Key": k1}
    cfg = client.get("/v1/tenant/config", headers=h1).json()
    assert cfg["is_demo"] is True                       # é uma demo (recursos travados)
    st = client.get("/v1/billing/status", headers=h1).json()
    assert st["routes_per_month"] == 5                  # cota própria de 5 rotas
    assert st["plan_id"] == "demo"
    # tem dados de materialidade (frota + telemetria semeadas)
    assert len(client.get("/v1/fleet", headers=h1).json()["vehicles"]) >= 10
    assert client.get("/v1/ingest/stats", headers=h1).json()["telemetry_records"] >= 100

    # a sessão é uma demo travada (recursos avançados bloqueados)
    assert client.get("/v1/billing/dev/activate?plan_id=essencial",
                      headers=h1).status_code == 403


def test_optimize_blocked_for_demo():
    body = {"vehicle_id": "rodotrem",
            "origins": [{"lat": -19.9, "lon": -48.1, "supply": 100}],
            "destinations": [{"lat": -19.97, "lon": -47.78, "demand": 100}]}
    r = client.post("/v1/optimize", json=body, headers=DEMO)
    assert r.status_code == 403
    assert "NOKAHI" in r.json()["detail"]


def test_ingest_blocked_for_demo():
    r = client.post("/v1/ingest/telemetry",
                    json={"source": "solinftec", "records": [{"CDEQUIPAMENTO": "1"}]}, headers=DEMO)
    assert r.status_code == 403
    r = client.post("/v1/ingest/alarms", json={"records": [{"CDEQUIPAMENTO": "1"}]}, headers=DEMO)
    assert r.status_code == 403


def test_connectors_blocked_for_demo():
    r = client.post("/v1/connectors", json={"name": "x", "type": "generic_http"}, headers=DEMO)
    assert r.status_code == 403


def test_billing_checkout_blocked_for_demo():
    r = client.post("/v1/billing/checkout", json={"plan_id": "essencial"}, headers=DEMO)
    assert r.status_code == 403


def test_demo_can_still_read_dashboard_and_intel():
    # recursos de leitura da degustação continuam liberados
    assert client.get("/v1/dashboard", headers=DEMO).status_code == 200
    assert client.get("/v1/intel/overview?n=100", headers=DEMO).status_code == 200
    assert client.get("/v1/fleet", headers=DEMO).status_code == 200


def test_non_demo_tenant_not_blocked():
    # /v1/connectors para o tenant "demo" (NÃO is_demo) não é bloqueado por demo
    r = client.post("/v1/connectors", json={"name": "c1", "type": "generic_http"},
                    headers={"X-API-Key": "demo-key"})
    assert r.status_code == 200
