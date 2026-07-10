"""Testes do configurador do Stripe (produtos/prices/.env) — sem rede real."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from agroroute import stripe_setup
from agroroute.billing import PLANS


def test_price_params_are_monthly_brl_in_cents():
    p = PLANS["essencial"]
    params = stripe_setup.price_params(p, "prod_1")
    assert params["currency"] == "brl"
    assert params["unit_amount"] == "290000"  # R$ 2.900,00
    assert params["recurring[interval]"] == "month"
    assert params["lookup_key"] == "nokahi_essencial_monthly"
    assert stripe_setup.price_params(PLANS["profissional"], "prod_2")["unit_amount"] == "590000"


def test_upsert_env_preserves_and_updates(tmp_path):
    env = tmp_path / ".env"
    env.write_text("STRIPE_SECRET_KEY=sk_test_x\nOUTRA=1\n", encoding="utf-8")
    stripe_setup.upsert_env(env, {"STRIPE_PRICE_ESSENCIAL": "price_a", "OUTRA": "2"})
    text = env.read_text(encoding="utf-8")
    assert "STRIPE_SECRET_KEY=sk_test_x" in text     # preservada
    assert "STRIPE_PRICE_ESSENCIAL=price_a" in text  # inserida
    assert "OUTRA=2" in text and "OUTRA=1" not in text  # atualizada, não duplicada


def _mock_stripe(existing_prices=None):
    existing_prices = existing_prices or {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/v1/prices":
            lk = request.url.params.get("lookup_keys[]")
            data = [{"id": existing_prices[lk]}] if lk in existing_prices else []
            return httpx.Response(200, json={"data": data})
        if request.method == "POST" and path == "/v1/products":
            return httpx.Response(200, json={"id": "prod_new"})
        if request.method == "POST" and path == "/v1/prices":
            return httpx.Response(200, json={"id": "price_new"})
        return httpx.Response(404, json={"error": "unhandled"})

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.stripe.com")


def test_run_creates_prices_and_writes_env(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    env = tmp_path / ".env"
    with _mock_stripe() as mock:
        out = stripe_setup.run(argv=["--env", str(env)], client=mock)
    assert out["updates"]["STRIPE_PRICE_ESSENCIAL"] == "price_new"
    assert out["updates"]["STRIPE_PRICE_PROFISSIONAL"] == "price_new"
    assert "STRIPE_PRICE_ESSENCIAL=price_new" in env.read_text(encoding="utf-8")


def test_run_reuses_existing_price(tmp_path, monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    env = tmp_path / ".env"
    existing = {"nokahi_essencial_monthly": "price_existing_e",
                "nokahi_profissional_monthly": "price_existing_p"}
    with _mock_stripe(existing) as mock:
        out = stripe_setup.run(argv=["--env", str(env)], client=mock)
    assert out["updates"]["STRIPE_PRICE_ESSENCIAL"] == "price_existing_e"
    assert out["updates"]["STRIPE_PRICE_PROFISSIONAL"] == "price_existing_p"


def test_dry_run_makes_no_calls(capsys):
    out = stripe_setup.run(argv=["--dry-run"])
    assert out["dry_run"] is True
    assert "essencial" in out["plans"]
