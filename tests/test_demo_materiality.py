"""A demo vem com dados (fictícios) para o lead ver a plataforma cheia."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import demo_seed
from agroroute.api import app

client = TestClient(app)
DEMO = {"X-API-Key": "demo-mg-2026"}


def test_dashboard_has_route_history_and_fleet():
    d = client.get("/v1/dashboard", headers=DEMO).json()
    assert d["routes"]["routes"] >= 50          # histórico de rotas semeado
    assert d["routes"]["total_km"] > 0 and d["routes"]["total_cost"] > 0
    assert d["fleet"]["total"] >= 10            # frota de manutenção
    assert len(d["recent_routes"]) >= 5


def test_ingested_telemetry_present():
    st = client.get("/v1/ingest/stats", headers=DEMO).json()
    assert st["telemetry_records"] >= 100
    assert st["alarm_records"] > 0
    assert st["equipments"] >= 50
    assert "solinftec" in st["by_source"]


def test_intelligence_uses_ingested_data():
    d = client.get("/v1/intel/overview", headers=DEMO).json()
    assert "ingerida" in d["fonte"]             # inteligência sobre dados reais
    assert d["kpis_manutencao"]["totalVeiculos"] >= 50
    assert d["alertas_preditivos"]["criticos"] + d["alertas_preditivos"]["altos"] >= 1


def test_seed_is_deterministic_and_idempotent():
    a, _ = demo_seed.generate_telemetry("t-x", 30)
    b, _ = demo_seed.generate_telemetry("t-x", 30)
    assert [r["equipment_id"] for r in a] == [r["equipment_id"] for r in b]
    assert len(a) == 30
