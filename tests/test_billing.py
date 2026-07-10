"""Testes do billing: trial, ativação, cota mensal e bloqueio na API."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from agroroute import api as api_mod
from agroroute.billing import PLANS, BillingStore

client = TestClient(api_mod.app)
KEY = {"X-API-Key": "demo-key"}  # tenant "demo"


@pytest.fixture()
def fresh_store(tmp_path, monkeypatch):
    store = BillingStore(tmp_path / "billing.json")
    monkeypatch.setattr(api_mod, "billing_store", store)
    return store


def test_new_tenant_gets_trial(fresh_store):
    sub = fresh_store.get_or_create("demo")
    assert sub.status == "trialing"
    assert sub.period_end > time.time()
    assert fresh_store.check_and_consume("demo").allowed


def test_expired_trial_blocks_and_activation_unblocks(fresh_store):
    sub = fresh_store.get_or_create("demo")
    sub.period_end = time.time() - 10
    fresh_store.update(sub)
    decision = fresh_store.check_and_consume("demo")
    assert not decision.allowed and "renove" in decision.reason

    fresh_store.activate("demo", "profissional")
    assert fresh_store.check_and_consume("demo").allowed
    assert fresh_store.get_or_create("demo").plan_id == "profissional"


def test_monthly_quota_enforced(fresh_store):
    fresh_store.activate("demo", "essencial")
    sub = fresh_store.get_or_create("demo")
    sub.routes_used_month = PLANS["essencial"].routes_per_month
    fresh_store.update(sub)
    decision = fresh_store.check_and_consume("demo")
    assert not decision.allowed and "cota" in decision.reason


def test_api_returns_402_without_valid_subscription(fresh_store):
    sub = fresh_store.get_or_create("demo")
    sub.status = "canceled"
    fresh_store.update(sub)
    job = {"origin_lat": -21.0, "origin_lon": -48.0, "dest_lat": -21.3, "dest_lon": -48.3}
    r = client.post("/v1/routes/compute", json=job, headers=KEY)
    assert r.status_code == 402


def test_plans_and_status_endpoints(fresh_store):
    r = client.get("/v1/billing/plans")
    assert r.status_code == 200
    assert set(r.json()) == {"essencial", "profissional", "enterprise"}
    assert "stripe_price_id" not in r.json()["essencial"]

    r = client.get("/v1/billing/status", headers=KEY)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "trialing"
    assert body["plan_name"] == "Essencial"


def test_sandbox_checkout_and_activate_flow(fresh_store):
    r = client.post("/v1/billing/checkout", json={"plan_id": "profissional"}, headers=KEY)
    assert r.status_code == 200
    assert r.json()["sandbox"] is True
    url = r.json()["checkout_url"]
    assert "/v1/billing/dev/activate" in url

    r = client.get("/v1/billing/dev/activate?plan_id=profissional", headers=KEY)
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = client.get("/v1/billing/status", headers=KEY)
    assert r.json()["plan_id"] == "profissional"
    assert r.json()["status"] == "active"


def test_stripe_webhook_lifecycle(fresh_store):
    from agroroute.billing import handle_stripe_event

    handle_stripe_event(
        {"type": "checkout.session.completed",
         "data": {"object": {"client_reference_id": "demo", "subscription": "sub_123",
                              "metadata": {"plan_id": "essencial"}}}},
        fresh_store,
    )
    assert fresh_store.get_or_create("demo").status == "active"

    handle_stripe_event(
        {"type": "invoice.payment_failed",
         "data": {"object": {"subscription": "sub_123"}}},
        fresh_store,
    )
    assert fresh_store.get_or_create("demo").status == "past_due"

    handle_stripe_event(
        {"type": "invoice.paid", "data": {"object": {"subscription": "sub_123"}}},
        fresh_store,
    )
    assert fresh_store.get_or_create("demo").status == "active"
