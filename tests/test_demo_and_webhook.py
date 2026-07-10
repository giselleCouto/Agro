"""Testes do modo demo (MG) e da verificação de assinatura do webhook Stripe."""
import hashlib
import hmac
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import billing
from agroroute.api import app

client = TestClient(app)


def test_demo_config_public_and_active():
    r = client.get("/v1/demo/config")
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["api_key"] == "demo-mg-2026"
    assert "Min, MG".replace("Min, ", "") or "MG" in cfg["region"]
    assert cfg["sample"]["origin"]["lat"] < -19  # Triângulo Mineiro

    # a demo já vem com assinatura ativa (degustação sem trial expirando)
    status = client.get("/v1/billing/status", headers={"X-API-Key": cfg["api_key"]}).json()
    assert status["status"] == "active"
    assert status["plan_id"] == "demo"


def test_demo_tenant_config_flag():
    r = client.get("/v1/tenant/config", headers={"X-API-Key": "demo-mg-2026"})
    assert r.status_code == 200
    body = r.json()
    assert body["is_demo"] is True
    assert any(z["name"] == "Uberaba" for z in body["avoid_zones"])


def test_webhook_rejects_bad_signature(monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    r = client.post("/v1/billing/webhook",
                    content=b'{"type":"x"}',
                    headers={"Stripe-Signature": "t=123,v1=deadbeef"})
    assert r.status_code == 400


def test_webhook_accepts_valid_signature(monkeypatch):
    secret = "whsec_test"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    payload = b'{"type":"ping","data":{"object":{}}}'
    t = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    r = client.post("/v1/billing/webhook", content=payload,
                    headers={"Stripe-Signature": f"t={t},v1={sig}"})
    assert r.status_code == 200


def test_verify_signature_unit():
    secret = "whsec_abc"
    payload = b'{"a":1}'
    t = str(int(time.time()))
    good = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    assert billing.verify_stripe_signature(payload, f"t={t},v1={good}", secret)
    assert not billing.verify_stripe_signature(payload, f"t={t},v1=zzzz", secret)
    assert not billing.verify_stripe_signature(payload, None, secret)
    old = str(int(time.time()) - 10000)  # fora da tolerância
    old_sig = hmac.new(secret.encode(), f"{old}.".encode() + payload, hashlib.sha256).hexdigest()
    assert not billing.verify_stripe_signature(payload, f"t={old},v1={old_sig}", secret)
