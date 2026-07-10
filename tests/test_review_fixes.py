"""Testes das correções apontadas pela revisão adversarial (billing/segurança)."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from agroroute import billing
from agroroute.billing import (
    BillingStore,
    create_checkout_session,
    handle_stripe_event,
    verify_stripe_signature,
)
from agroroute.leads import _RateLimiter


def test_invoice_paid_does_not_resurrect_canceled(tmp_path):
    store = BillingStore(tmp_path / "b.json")
    handle_stripe_event({"id": "evt_1", "type": "checkout.session.completed",
                         "data": {"object": {"client_reference_id": "t", "subscription": "sub_1",
                                             "metadata": {"plan_id": "essencial"}}}}, store)
    handle_stripe_event({"id": "evt_2", "type": "customer.subscription.deleted",
                         "data": {"object": {"id": "sub_1"}}}, store)
    assert store.get_or_create("t").status == "canceled"
    # invoice.paid tardio/reordenado NÃO deve reativar
    handle_stripe_event({"id": "evt_3", "type": "invoice.paid",
                         "data": {"object": {"subscription": "sub_1"}}}, store)
    assert store.get_or_create("t").status == "canceled"


def test_webhook_event_dedup(tmp_path):
    store = BillingStore(tmp_path / "b.json")
    handle_stripe_event({"id": "evt_x", "type": "checkout.session.completed",
                         "data": {"object": {"client_reference_id": "t", "subscription": "s",
                                             "metadata": {"plan_id": "essencial"}}}}, store)
    # cancela e tenta reprocessar o MESMO id de ativação: deve ser ignorado
    store.get_or_create("t")
    canceled = store.activate("t", "essencial")
    canceled.status = "canceled"; store.update(canceled)
    r = handle_stripe_event({"id": "evt_x", "type": "checkout.session.completed",
                             "data": {"object": {"client_reference_id": "t", "subscription": "s",
                                                 "metadata": {"plan_id": "essencial"}}}}, store)
    assert "duplicado" in r
    assert store.get_or_create("t").status == "canceled"


def test_signature_accepts_multiple_v1():
    import hashlib, hmac
    secret = "whsec_x"
    payload = b'{"a":1}'
    t = str(int(time.time()))
    good = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    header = f"t={t},v1=badbad,v1={good}"   # rotação de secret: vários v1
    assert verify_stripe_signature(payload, header, secret)


def test_checkout_raises_when_stripe_set_but_price_missing(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.delenv("STRIPE_PRICE_ESSENCIAL", raising=False)
    plan = billing.PLANS["essencial"]

    async def run():
        import httpx
        async with httpx.AsyncClient() as c:
            await create_checkout_session("t", plan, "http://x", c)

    with pytest.raises(RuntimeError):
        asyncio.run(run())


def test_rate_limiter_prunes_stale_ips():
    rl = _RateLimiter(limit=1, window=1, max_ips=5)
    for i in range(50):
        rl.allow(f"10.0.0.{i}")
    # depois de expirar a janela, uma nova chamada dispara a poda
    time.sleep(1.1)
    rl.allow("10.0.1.1")
    assert len(rl._hits) <= 6  # bem abaixo dos 50 IPs vistos


def test_refresh_marks_past_due(tmp_path):
    store = BillingStore(tmp_path / "b.json")
    sub = store.get_or_create("t")
    sub.period_end = time.time() - 10
    store.update(sub)
    refreshed = store.refresh("t")
    assert refreshed.status == "past_due"
