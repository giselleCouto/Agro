"""Testes da configuração de domínio/deploy (PUBLIC_BASE_URL, host, health)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import api as api_mod
from agroroute.api import app

client = TestClient(app)
KEY = {"X-API-Key": "demo-key"}


def test_public_base_url_used_in_checkout(monkeypatch):
    monkeypatch.setattr(api_mod, "PUBLIC_BASE_URL", "https://agroroute.despaxai.com")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)  # modo sandbox
    r = client.post("/v1/billing/checkout", json={"plan_id": "essencial"}, headers=KEY)
    assert r.status_code == 200
    assert r.json()["checkout_url"].startswith("https://agroroute.despaxai.com/")


def test_public_base_url_falls_back_to_request(monkeypatch):
    monkeypatch.setattr(api_mod, "PUBLIC_BASE_URL", "")
    r = client.post("/v1/billing/checkout", json={"plan_id": "essencial"}, headers=KEY)
    assert r.status_code == 200
    # sem PUBLIC_BASE_URL, deriva do request (TestClient = http://testserver)
    assert "testserver" in r.json()["checkout_url"]


def test_health_ok():
    assert client.get("/v1/health").json()["status"] == "ok"
