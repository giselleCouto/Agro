"""Assinatura mensal recorrente por tenant — lastreada em banco.

Planos com preço mensal e cota de rotas. Cobrança recorrente via Stripe
(Checkout mode=subscription + webhooks). Sem `STRIPE_SECRET_KEY`, roda em
modo *sandbox*: o checkout devolve uma URL local que ativa a assinatura.

Para ativar a cobrança real:
  1. `python -m agroroute.stripe_setup`  (cria produtos e prices e grava .env)
  2. configure o webhook do Stripe para POST /v1/billing/webhook
  3. defina STRIPE_WEBHOOK_SECRET

Enforcement: os endpoints de cálculo exigem assinatura ativa (ou trial) e cota
mensal; cada rota consome 1 da cota.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError

from .db import SubscriptionRow, WebhookEventRow, make_engine, session_factory, write_lock

STRIPE_API = "https://api.stripe.com/v1"
TRIAL_DAYS = 14
MONTH_SECONDS = 30 * 24 * 3600
WEBHOOK_TOLERANCE_S = 300


class Plan(BaseModel):
    id: str
    name: str
    price_month_brl: float
    routes_per_month: int
    description: str
    public: bool = True                    # aparece na vitrine de preços?
    stripe_price_id: Optional[str] = None


PLANS: dict[str, Plan] = {
    "demo": Plan(
        id="demo", name="Demonstração", price_month_brl=0.0,
        routes_per_month=300, public=False,
        description="Degustação da plataforma na região do Triângulo Mineiro (MG)",
    ),
    # Preços por USINA/mês, calibrados para margem BRUTA >= 80% (custo direto de
    # hospedagem+suporte ~R$ 2,2k/usina/mês). Ver BUSINESS_CASE.md.
    "essencial": Plan(
        id="essencial", name="Essencial", price_month_brl=10900.0,
        routes_per_month=3000,
        description="1 usina · até 3.000 rotas/mês · cobertura Brasil · clima real e pedágio por eixo",
    ),
    "profissional": Plan(
        id="profissional", name="Profissional", price_month_brl=18900.0,
        routes_per_month=25000,
        description="Grupo/multi-usina · 25.000 rotas/mês · roteirizador dedicado · API · suporte prioritário",
    ),
    "enterprise": Plan(
        id="enterprise", name="Enterprise", price_month_brl=0.0,
        routes_per_month=10**9,
        description="Frota ilimitada · SLA · integração telemetria/ERP · sob consulta",
    ),
}


def public_plans() -> dict[str, Plan]:
    return {pid: p for pid, p in PLANS.items() if p.public}


def price_id_for(plan: Plan) -> str | None:
    """Price ID recorrente mensal do Stripe (resolvido em tempo de chamada)."""
    return os.environ.get(f"STRIPE_PRICE_{plan.id.upper()}") or plan.stripe_price_id


class Subscription(BaseModel):
    tenant_id: str
    plan_id: str = "essencial"
    status: str = "trialing"          # trialing | active | past_due | canceled
    period_end: float = 0.0
    routes_used_month: int = 0
    usage_month: str = ""
    provider: str = "sandbox"         # sandbox | stripe
    provider_sub_id: Optional[str] = None
    stripe_customer_id: Optional[str] = None

    @classmethod
    def from_row(cls, row: SubscriptionRow) -> "Subscription":
        return cls(
            tenant_id=row.tenant_id, plan_id=row.plan_id, status=row.status,
            period_end=row.period_end or 0.0,
            routes_used_month=row.routes_used_month or 0,
            usage_month=row.usage_month or "", provider=row.provider or "sandbox",
            provider_sub_id=row.provider_sub_id, stripe_customer_id=row.stripe_customer_id,
        )


@dataclass
class BillingDecision:
    allowed: bool
    reason: str = ""


class BillingStore:
    """Persistência de assinaturas no banco (ver [db.py](db.py))."""

    def __init__(self, storage: str | Path | None = None, engine=None):
        if engine is None and storage is not None:
            p = Path(storage)
            db_path = p.with_suffix(".db") if p.suffix else p / "billing.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            engine = make_engine(f"sqlite:///{db_path.as_posix()}")
        self._Session = session_factory(engine)

    def _apply(self, row: SubscriptionRow, sub: Subscription) -> None:
        row.plan_id = sub.plan_id
        row.status = sub.status
        row.period_end = sub.period_end
        row.routes_used_month = sub.routes_used_month
        row.usage_month = sub.usage_month
        row.provider = sub.provider
        row.provider_sub_id = sub.provider_sub_id
        row.stripe_customer_id = sub.stripe_customer_id

    def get_or_create(self, tenant_id: str) -> Subscription:
        with write_lock(), self._Session() as s:
            row = s.get(SubscriptionRow, tenant_id)
            if row is None:
                row = SubscriptionRow(
                    tenant_id=tenant_id, plan_id="essencial", status="trialing",
                    period_end=time.time() + TRIAL_DAYS * 24 * 3600,
                    routes_used_month=0, usage_month=_current_month(), provider="sandbox",
                )
                s.add(row)
                s.commit()
            return Subscription.from_row(row)

    def update(self, sub: Subscription) -> None:
        with write_lock(), self._Session() as s:
            row = s.get(SubscriptionRow, sub.tenant_id)
            if row is None:
                row = SubscriptionRow(tenant_id=sub.tenant_id)
                s.add(row)
            self._apply(row, sub)
            s.commit()

    def seed(self, sub: Subscription) -> None:
        """Cria a assinatura só se ainda não existir (para semear a demo)."""
        with write_lock(), self._Session() as s:
            if s.get(SubscriptionRow, sub.tenant_id) is None:
                row = SubscriptionRow(tenant_id=sub.tenant_id)
                self._apply(row, sub)
                s.add(row)
                s.commit()

    def activate(self, tenant_id: str, plan_id: str, provider: str = "sandbox",
                 provider_sub_id: str | None = None,
                 stripe_customer_id: str | None = None) -> Subscription:
        sub = self.get_or_create(tenant_id)
        sub.plan_id = plan_id
        sub.status = "active"
        sub.period_end = time.time() + MONTH_SECONDS
        sub.provider = provider
        if provider_sub_id:
            sub.provider_sub_id = provider_sub_id
        if stripe_customer_id:
            sub.stripe_customer_id = stripe_customer_id
        self.update(sub)
        return sub

    def refresh(self, tenant_id: str) -> Subscription:
        """Reaplica reset mensal + transição de expiração sem consumir cota.

        Mantém `/v1/billing/status` coerente mesmo sem cálculo de rota recente.
        """
        with write_lock(), self._Session() as s:
            row = s.get(SubscriptionRow, tenant_id)
            if row is None:
                row = SubscriptionRow(
                    tenant_id=tenant_id, plan_id="essencial", status="trialing",
                    period_end=time.time() + TRIAL_DAYS * 24 * 3600,
                    routes_used_month=0, usage_month=_current_month(), provider="sandbox",
                )
                s.add(row)
            now = time.time()
            month = _current_month()
            if row.usage_month != month:
                row.usage_month = month
                row.routes_used_month = 0
            if row.status in ("trialing", "active") and now > (row.period_end or 0):
                row.status = "past_due"
            s.commit()
            return Subscription.from_row(row)

    def find_by_provider_sub(self, sub_id: str) -> Subscription | None:
        with self._Session() as s:
            row = s.query(SubscriptionRow).filter(
                SubscriptionRow.provider_sub_id == sub_id
            ).first()
            return Subscription.from_row(row) if row else None

    def mark_event(self, event_id: str | None) -> bool:
        """Dedup de webhook: True se novo (processar), False se já visto."""
        if not event_id:
            return True
        with write_lock(), self._Session() as s:
            if s.get(WebhookEventRow, event_id) is not None:
                return False
            s.add(WebhookEventRow(event_id=event_id))
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return False
            return True

    def check_and_consume(self, tenant_id: str, n_routes: int = 1) -> BillingDecision:
        """Valida assinatura e consome cota atômicamente.

        O `with_for_update()` bloqueia a linha no Postgres (multi-worker);
        no SQLite é no-op, mas o `write_lock` global serializa as escritas.
        """
        with write_lock(), self._Session() as s:
            row = (
                s.query(SubscriptionRow)
                .filter(SubscriptionRow.tenant_id == tenant_id)
                .with_for_update()
                .first()
            )
            if row is None:
                row = SubscriptionRow(
                    tenant_id=tenant_id, plan_id="essencial", status="trialing",
                    period_end=time.time() + TRIAL_DAYS * 24 * 3600,
                    routes_used_month=0, usage_month=_current_month(), provider="sandbox",
                )
                s.add(row)
            now = time.time()
            month = _current_month()
            if row.usage_month != month:
                row.usage_month = month
                row.routes_used_month = 0
            if row.status == "canceled":
                s.commit()
                return BillingDecision(False, "assinatura cancelada — reative nos planos")
            if row.status in ("trialing", "active") and now > (row.period_end or 0):
                row.status = "past_due"
            if row.status == "past_due":
                s.commit()
                return BillingDecision(
                    False,
                    "período expirado — renove a assinatura para continuar calculando rotas",
                )
            plan = PLANS.get(row.plan_id, PLANS["essencial"])
            if (row.routes_used_month or 0) + n_routes > plan.routes_per_month:
                s.commit()
                return BillingDecision(
                    False,
                    f"cota mensal do plano {plan.name} atingida "
                    f"({plan.routes_per_month} rotas/mês) — faça upgrade",
                )
            row.routes_used_month = (row.routes_used_month or 0) + n_routes
            s.commit()
            return BillingDecision(True)


def _current_month() -> str:
    return time.strftime("%Y-%m")


def ensure_demo_subscription(store: BillingStore, tenant_id: str,
                             plan_id: str = "demo") -> None:
    """Garante uma assinatura demo ativa e perene para o tenant de degustação."""
    store.seed(Subscription(
        tenant_id=tenant_id, plan_id=plan_id, status="active",
        period_end=time.time() + 3650 * 24 * 3600, provider="demo",
        usage_month=_current_month(),
    ))


# ---------------------------------------------------------------------------
# Stripe
# ---------------------------------------------------------------------------

def stripe_key() -> str | None:
    return os.environ.get("STRIPE_SECRET_KEY")


def webhook_secret() -> str | None:
    return os.environ.get("STRIPE_WEBHOOK_SECRET")


def verify_stripe_signature(payload: bytes, sig_header: str | None,
                            secret: str, tolerance: int = WEBHOOK_TOLERANCE_S) -> bool:
    """Valida o cabeçalho `Stripe-Signature` (esquema t=…,v1=…) via HMAC-SHA256."""
    if not sig_header:
        return False
    t = None
    v1_sigs: list[str] = []
    for part in sig_header.split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k == "t":
            t = v
        elif k == "v1":
            v1_sigs.append(v)  # pode haver várias durante rotação de secret
    if not t or not v1_sigs:
        return False
    try:
        if abs(time.time() - int(t)) > tolerance:
            return False
    except ValueError:
        return False
    signed = f"{t}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in v1_sigs)


async def create_checkout_session(
    tenant_id: str, plan: Plan, base_url: str, client: httpx.AsyncClient
) -> str:
    """URL de checkout para assinar o plano (recorrência mensal)."""
    key = stripe_key()
    price_id = price_id_for(plan)
    if not key:
        # sem Stripe configurado: atalho sandbox (apenas desenvolvimento)
        return f"{base_url}/v1/billing/dev/activate?plan_id={plan.id}"
    if not price_id:
        # Stripe configurado mas price ausente: erro de configuração, NÃO
        # cair no sandbox (isso liberaria assinatura de graça em produção)
        raise RuntimeError(
            f"price do plano '{plan.id}' não configurado — rode "
            f"`python -m agroroute.stripe_setup` para criar e gravar no .env"
        )
    r = await client.post(
        f"{STRIPE_API}/checkout/sessions",
        auth=(key, ""),
        data={
            "mode": "subscription",
            "line_items[0][price]": price_id,
            "line_items[0][quantity]": "1",
            "client_reference_id": tenant_id,
            "metadata[plan_id]": plan.id,
            "metadata[tenant_id]": tenant_id,
            "subscription_data[metadata][plan_id]": plan.id,
            "subscription_data[metadata][tenant_id]": tenant_id,
            "success_url": f"{base_url}/app?billing=success",
            "cancel_url": f"{base_url}/app?billing=cancel",
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["url"]


def handle_stripe_event(event: dict, store: BillingStore) -> str:
    """Processa eventos do webhook Stripe relevantes para a recorrência.

    Idempotente: o Stripe entrega at-least-once e fora de ordem, então cada
    event.id é processado uma única vez, e `invoice.paid` nunca ressuscita uma
    assinatura cancelada.
    """
    if not store.mark_event(event.get("id")):
        return "evento duplicado (ignorado)"
    etype = event.get("type", "")
    obj = event.get("data", {}).get("object", {})
    if etype == "checkout.session.completed":
        tenant_id = obj.get("client_reference_id") or obj.get("metadata", {}).get("tenant_id")
        sub_id = obj.get("subscription")
        customer = obj.get("customer")
        plan_id = obj.get("metadata", {}).get("plan_id", "essencial")
        if tenant_id:
            store.activate(tenant_id, plan_id, provider="stripe",
                           provider_sub_id=sub_id, stripe_customer_id=customer)
            return f"ativada assinatura de {tenant_id}"
    elif etype == "invoice.paid":
        sub_id = obj.get("subscription")
        found = store.find_by_provider_sub(sub_id) if sub_id else None
        # não ressuscita assinatura cancelada (evento tardio/reordenado)
        if found and found.status != "canceled":
            found.status = "active"
            found.period_end = time.time() + MONTH_SECONDS
            store.update(found)
            return f"renovada assinatura de {found.tenant_id}"
    elif etype in ("invoice.payment_failed", "customer.subscription.deleted"):
        sub_id = obj.get("subscription") or obj.get("id")
        found = store.find_by_provider_sub(sub_id) if sub_id else None
        if found:
            found.status = "past_due" if etype == "invoice.payment_failed" else "canceled"
            store.update(found)
            return f"{found.tenant_id}: {found.status}"
    return "evento ignorado"
