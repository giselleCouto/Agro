"""Testes de captura de leads: gravação, honeypot, listagem admin, validação."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute.api import app

client = TestClient(app)
ADMIN = {"X-Admin-Token": "test-admin-token"}

VALID = {
    "name": "João da Silva", "email": "joao@usinaexemplo.com.br",
    "company": "Usina Exemplo", "phone": "34 99999-0000",
    "role": "Gerente de logística", "fleet_size": "51–200 caminhões",
    "message": "Quero reduzir o custo do transporte da safra.",
}


def test_lead_created_and_listed():
    r = client.post("/v1/leads", json=VALID)
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["id"]

    r = client.get("/v1/admin/leads", headers=ADMIN)
    assert r.status_code == 200
    emails = [l["email"] for l in r.json()["leads"]]
    assert "joao@usinaexemplo.com.br" in emails


def test_honeypot_silently_ignored():
    before = client.get("/v1/admin/leads", headers=ADMIN).json()["count"]
    r = client.post("/v1/leads", json={**VALID, "email": "bot@x.com", "website": "http://spam"})
    assert r.status_code == 200
    assert r.json()["id"] is None
    after = client.get("/v1/admin/leads", headers=ADMIN).json()["count"]
    assert after == before  # não gravou


def test_invalid_email_rejected():
    r = client.post("/v1/leads", json={**VALID, "email": "sem-arroba"})
    assert r.status_code == 422


def test_admin_requires_token():
    assert client.get("/v1/admin/leads").status_code in (401, 422)
    assert client.get("/v1/admin/leads", headers={"X-Admin-Token": "errado"}).status_code == 401


def test_lead_status_update():
    lead_id = client.post("/v1/leads", json={**VALID, "email": "status@x.com"}).json()["id"]
    r = client.post(f"/v1/admin/leads/{lead_id}/status", json={"status": "contatado"}, headers=ADMIN)
    assert r.status_code == 200
    leads = client.get("/v1/admin/leads", headers=ADMIN).json()["leads"]
    got = next(l for l in leads if l["id"] == lead_id)
    assert got["status"] == "contatado"
    # status inválido
    assert client.post(f"/v1/admin/leads/{lead_id}/status", json={"status": "x"}, headers=ADMIN).status_code == 422
