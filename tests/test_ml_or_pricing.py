"""Testes de ML, Pesquisa Operacional, precificação por uso e agente analítico."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import or_opt
from agroroute.api import app
from agroroute.ml import DemandForecaster, FuelCalibrator, MaintenanceRiskModel
from agroroute.pricing import QuoteRequest, quote

client = TestClient(app)
DEMO = {"X-API-Key": "demo-mg-2026"}
NONDEMO = {"X-API-Key": "demo-key"}   # tenant "demo" (não is_demo) p/ recursos travados na demo


# ---- ML ----
def test_fuel_calibrator_learns_factor():
    pred = [100, 200, 300, 400]
    actual = [115, 230, 345, 460]      # real = 1.15 x previsto
    cal = FuelCalibrator().fit(pred, actual)
    assert abs(cal.factor - 1.15) < 0.01
    assert cal.r2 > 0.99
    assert abs(cal.apply(100) - 115) < 1


def test_maintenance_risk_monotonic():
    m = MaintenanceRiskModel()
    low = m.risk_from_component(20, 0.2)
    high = m.risk_from_component(95, 0.95)
    assert 0 <= low < high <= 1
    assert high > 0.7
    assert MaintenanceRiskModel.label(0.8) == "crítico"


def test_maintenance_risk_trainable():
    X = [[0.1, 0.1, 0.2, 0.5], [0.9, 0.9, 0.5, 0.8], [0.2, 0.2, 0.3, 0.5], [0.95, 0.95, 0.6, 0.9]]
    y = [0, 1, 0, 1]
    m = MaintenanceRiskModel().fit(X, y)
    assert m.risk([0.95, 0.95, 0.6, 0.9]) > m.risk([0.1, 0.1, 0.2, 0.5])


def test_demand_forecaster_trend():
    series = [10, 12, 14, 16, 18, 20, 22, 24]  # tendência de alta
    fc = DemandForecaster().fit(series)
    forecast = fc.forecast(3)
    assert fc.slope > 0
    assert all(v > 0 for v in forecast)
    assert forecast[-1] >= forecast[0]


# ---- Pesquisa Operacional ----
def test_transportation_optimal():
    r = or_opt.solve_transportation([10, 10], [8, 12], [[1, 2], [3, 1]])
    assert r["success"]
    assert r["delivered"] == 20
    assert abs(r["total_cost"] - 22.0) < 0.01   # ótimo conhecido


def test_assignment_hungarian():
    r = or_opt.solve_assignment([[4, 2], [3, 1]])
    assert abs(r["total_cost"] - 5.0) < 0.01
    assert r["n_assigned"] == 2


def test_allocate_trips_respects_capacity():
    # 2 veículos, 1 viagem cada; 3 rotas -> 1 rota fica sem veículo
    r = or_opt.allocate_trips_to_vehicles([[5, 9, 3], [4, 2, 8]], [1, 1])
    assert len(r["assignments"]) == 2
    assert len(r["unassigned_routes"]) == 1


# ---- Precificação por uso ----
def test_quote_dimensions_and_margin():
    q = quote(QuoteRequest(vehicles=30, routes_per_month=4000, origins=60, destinations=3))
    assert q["monthly_total"] == 13025.0
    assert q["gross_margin_pct"] >= 80.0
    # confere que os 4 drivers entram na conta
    labels = " ".join(i["item"] for i in q["items"])
    assert "Veículos" in labels and "Rotas" in labels and "Origens" in labels and "Destinos" in labels


def test_quote_endpoint():
    r = client.post("/v1/billing/quote",
                    json={"vehicles": 10, "routes_per_month": 800, "origins": 20, "destinations": 1})
    assert r.status_code == 200
    assert r.json()["monthly_total"] > 0


# ---- Endpoints OR / assistente / ML ----
def test_optimize_endpoint():
    body = {
        "vehicle_id": "rodotrem",
        "origins": [{"name": "Talhão A", "lat": -19.85, "lon": -48.52, "supply": 140},
                    {"name": "Talhão B", "lat": -19.95, "lon": -48.20, "supply": 140}],
        "destinations": [{"name": "Usina Delta", "lat": -19.97, "lon": -47.78, "demand": 200}],
    }
    r = client.post("/v1/optimize", json=body, headers=NONDEMO)
    assert r.status_code == 200
    d = r.json()
    assert d["total_cost"] > 0
    assert d["total_trips"] >= 1
    assert len(d["plan"]) >= 1


def test_assistant_answers_maintenance():
    r = client.post("/v1/assistant", json={"question": "quantos caminhões precisam de manutenção?"}, headers=DEMO)
    assert r.status_code == 200
    body = r.json()
    assert "answer" in body and len(body["answer"]) > 10


def test_assistant_help_has_suggestions():
    r = client.post("/v1/assistant", json={"question": "ajuda"}, headers=DEMO)
    assert r.json()["data"]["suggestions"]


def test_ml_maintenance_risk_endpoint():
    r = client.get("/v1/ml/maintenance-risk", headers=DEMO)
    assert r.status_code == 200
    vs = r.json()["vehicles"]
    assert len(vs) >= 3
    assert all("components" in v for v in vs)
    assert all("risk_pct" in c for c in vs[0]["components"])
