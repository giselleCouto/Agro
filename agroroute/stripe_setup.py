"""Cria os produtos e prices recorrentes mensais no Stripe e grava o .env.

Uso:
    # exporte a chave (ou coloque em .env) e rode:
    setx STRIPE_SECRET_KEY sk_test_...        # Windows (nova sessão)
    python -m agroroute.stripe_setup

    # opcional: também cria o endpoint de webhook e grava STRIPE_WEBHOOK_SECRET
    python -m agroroute.stripe_setup --webhook-url https://api.suaempresa.com/v1/billing/webhook

    # só mostra o que faria, sem chamar o Stripe
    python -m agroroute.stripe_setup --dry-run

Idempotente: a reexecução reaproveita o price existente (casado por lookup_key)
e não duplica produtos. Prices no Stripe são imutáveis — para trocar o valor,
o script cria um novo price e reaponta o lookup_key.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import httpx

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    load_dotenv = lambda *a, **k: None  # noqa: E731

from .billing import PLANS

STRIPE_API = "https://api.stripe.com/v1"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "invoice.paid",
    "invoice.payment_failed",
    "customer.subscription.deleted",
]


def lookup_key(plan_id: str) -> str:
    return f"nokahi_{plan_id}_monthly"


def product_params(plan) -> dict:
    return {
        "name": f"Peabiru Agro — {plan.name}",
        "description": plan.description,
        "metadata[nokahi_plan]": plan.id,
    }


def price_params(plan, product_id: str) -> dict:
    """Price recorrente mensal em BRL. Valor em centavos."""
    return {
        "currency": "brl",
        "unit_amount": str(int(round(plan.price_month_brl * 100))),
        "recurring[interval]": "month",
        "product": product_id,
        "lookup_key": lookup_key(plan.id),
        "transfer_lookup_key": "true",
        "nickname": f"{plan.name} mensal",
        "metadata[nokahi_plan]": plan.id,
    }


def _post(client: httpx.Client, path: str, data: dict) -> dict:
    r = client.post(f"{STRIPE_API}{path}", data=data)
    if r.status_code >= 400:
        raise RuntimeError(f"Stripe {path} -> {r.status_code}: {r.text}")
    return r.json()


def _get(client: httpx.Client, path: str, params: dict) -> dict:
    r = client.get(f"{STRIPE_API}{path}", params=params)
    if r.status_code >= 400:
        raise RuntimeError(f"Stripe {path} -> {r.status_code}: {r.text}")
    return r.json()


def ensure_price(client: httpx.Client, plan) -> tuple[str, bool]:
    """Devolve (price_id, created). Reaproveita price existente pelo lookup_key."""
    existing = _get(client, "/prices", {"lookup_keys[]": lookup_key(plan.id), "limit": 1})
    data = existing.get("data", [])
    if data:
        return data[0]["id"], False
    product = _post(client, "/products", product_params(plan))
    price = _post(client, "/prices", price_params(plan, product["id"]))
    return price["id"], True


def ensure_webhook(client: httpx.Client, url: str) -> str:
    """Cria (ou reaproveita) o endpoint de webhook e devolve o signing secret."""
    listed = _get(client, "/webhook_endpoints", {"limit": 100})
    for ep in listed.get("data", []):
        if ep.get("url") == url:
            # o secret só é retornado na criação; reusa o endpoint existente
            return ep.get("secret", "")
    data = {"url": url}
    for i, ev in enumerate(WEBHOOK_EVENTS):
        data[f"enabled_events[{i}]"] = ev
    ep = _post(client, "/webhook_endpoints", data)
    return ep.get("secret", "")


def upsert_env(path: Path, updates: dict[str, str]) -> None:
    """Insere/atualiza chaves no .env preservando o resto do arquivo."""
    lines: list[str] = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    keys = set(updates)
    out = []
    seen = set()
    for line in lines:
        k = line.split("=", 1)[0].strip() if "=" in line else None
        if k in keys:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k in keys - seen:
        out.append(f"{k}={updates[k]}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def run(argv: list[str] | None = None, client: httpx.Client | None = None) -> dict:
    parser = argparse.ArgumentParser(description="Configura os produtos/prices do Stripe")
    parser.add_argument("--webhook-url", default=None,
                        help="URL pública do webhook (cria o endpoint e grava o secret)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--env", default=str(ENV_PATH))
    args = parser.parse_args(argv)

    load_dotenv(args.env)
    key = os.environ.get("STRIPE_SECRET_KEY")

    paid = [p for p in PLANS.values() if p.price_month_brl > 0]

    if args.dry_run:
        plan = {}
        for p in paid:
            plan[p.id] = {"lookup_key": lookup_key(p.id),
                          "unit_amount": int(round(p.price_month_brl * 100)),
                          "price_params": price_params(p, "prod_XXXX")}
        print("[dry-run] planos que seriam criados:")
        for pid, info in plan.items():
            print(f"  {pid}: {info['unit_amount']} centavos/mês (lookup {info['lookup_key']})")
        return {"dry_run": True, "plans": plan}

    if not key:
        print("ERRO: defina STRIPE_SECRET_KEY (env ou .env) antes de rodar.", file=sys.stderr)
        raise SystemExit(2)

    own_client = client is None
    client = client or httpx.Client(auth=(key, ""), timeout=30)
    updates: dict[str, str] = {}
    try:
        for p in paid:
            price_id, created = ensure_price(client, p)
            updates[f"STRIPE_PRICE_{p.id.upper()}"] = price_id
            print(f"  {p.name}: {price_id} ({'criado' if created else 'reaproveitado'})")
        if args.webhook_url:
            secret = ensure_webhook(client, args.webhook_url)
            if secret:
                updates["STRIPE_WEBHOOK_SECRET"] = secret
                print(f"  webhook: {args.webhook_url} (secret gravado)")
            else:
                print(f"  webhook: {args.webhook_url} já existia — reveja o secret no painel")
    finally:
        if own_client:
            client.close()

    upsert_env(Path(args.env), updates)
    print(f"\n.env atualizado em {args.env}. Reinicie a API para carregar as chaves.")
    return {"updates": updates}


if __name__ == "__main__":
    run()
