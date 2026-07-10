"""API HTTP do NOKAHI AgroRoute (FastAPI).

Multi-tenant via header `X-API-Key`, com banco de dados (SQLAlchemy), assinatura
mensal recorrente (Stripe), modo demo público (Triângulo Mineiro / MG) e captura
de leads.

Web:
  GET  /                 landing page comercial (com formulário de contato)
  GET  /app              aplicação de roteirização
  GET  /admin            painel de leads (token de admin)

API:
  GET  /v1/health
  GET  /v1/tenant/config · GET /v1/vehicles
  POST /v1/routes/compute · POST /v1/routes/batch
  GET  /v1/billing/plans · /v1/billing/status · POST /v1/billing/checkout · webhook
  GET  /v1/demo/config
  POST /v1/leads         (público) · GET /v1/admin/leads (admin)
"""
from __future__ import annotations

import hmac
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# carrega .env ANTES de qualquer import que leia variáveis de ambiente
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx  # noqa: E402
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from . import __version__  # noqa: E402
from .billing import (  # noqa: E402
    PLANS,
    BillingStore,
    create_checkout_session,
    ensure_demo_subscription,
    handle_stripe_event,
    public_plans,
    stripe_key,
    verify_stripe_signature,
    webhook_secret,
)
from . import or_opt  # noqa: E402
from .assistant import AnalyticalAgent  # noqa: E402
from .db import get_engine  # noqa: E402
from .fleet import (  # noqa: E402
    DEMO_VEHICLES,
    RouteLogStore,
    VehicleIn,
    VehicleStore,
    fleet_summary,
)
from .geo import haversine_km  # noqa: E402
from .leads import LeadIn, LeadStore  # noqa: E402
from .ml import DemandForecaster, FuelCalibrator, MaintenanceRiskModel  # noqa: E402
from .notify import send_lead_notification  # noqa: E402
from .pricing import PRICE, QuoteRequest, quote  # noqa: E402
from .models import (  # noqa: E402
    DEFAULT_FLEET,
    BatchRouteRequest,
    BatchRouteResponse,
    RouteJob,
    RouteJobResult,
    TenantConfig,
)
from .service import compute_batch  # noqa: E402
from .tenancy import TenantStore  # noqa: E402

TENANTS_PATH = os.environ.get(
    "AGROROUTE_TENANTS",
    str(Path(__file__).resolve().parent.parent / "data" / "tenants.json"),
)
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
CONTACT_EMAIL = "contato@nokahi.com"
DEMO_TENANT_ID = "demo-mg"
# sem default inseguro: se não configurado, os endpoints de admin ficam desativados
ADMIN_TOKEN = os.environ.get("AGROROUTE_ADMIN_TOKEN")
# só confia em X-Forwarded-For atrás de um proxy reverso confiável
TRUST_PROXY = os.environ.get("AGROROUTE_TRUST_PROXY", "").lower() in ("1", "true", "yes")

app = FastAPI(
    title="NOKAHI AgroRoute",
    version=__version__,
    description="Roteirização econômica multi-tenant para frotas agrícolas pesadas",
)

# banco compartilhado por todos os stores
_engine = get_engine()
store = TenantStore(TENANTS_PATH, engine=_engine)
billing_store = BillingStore(engine=_engine)
lead_store = LeadStore(engine=_engine)
vehicle_store = VehicleStore(engine=_engine)
route_log = RouteLogStore(engine=_engine)
agent = AnalyticalAgent(vehicle_store, route_log, billing_store, PLANS)
_risk_model = MaintenanceRiskModel()

# assinatura demo perene para o tenant de degustação (MG)
if store.by_id(DEMO_TENANT_ID):
    ensure_demo_subscription(billing_store, DEMO_TENANT_ID)

# frota de exemplo para dashboard/manutenção (idempotente)
for _tid, _vehicles in DEMO_VEHICLES.items():
    if store.by_id(_tid):
        vehicle_store.seed(_tid, _vehicles)


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------

def get_tenant(x_api_key: str = Header(...)) -> TenantConfig:
    tenant = store.by_api_key(x_api_key)
    if tenant is None:
        raise HTTPException(status_code=401, detail="API key inválida")
    return tenant


def require_admin(x_admin_token: str = Header(default="")) -> None:
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="painel admin desativado — configure AGROROUTE_ADMIN_TOKEN",
        )
    # compara em bytes (evita TypeError de compare_digest com header não-ASCII)
    if not hmac.compare_digest(x_admin_token.encode("utf-8"), ADMIN_TOKEN.encode("utf-8")):
        raise HTTPException(status_code=401, detail="token de admin inválido")


def client_ip(request: Request) -> str:
    # só confia no cabeçalho de proxy quando explicitamente habilitado
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(WEB_DIR / "landing.html")


@app.get("/app", include_in_schema=False)
def app_page():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/admin", include_in_schema=False)
def admin_page():
    return FileResponse(WEB_DIR / "admin.html")


# ---------------------------------------------------------------------------
# Núcleo de roteirização
# ---------------------------------------------------------------------------

@app.get("/v1/health")
def health():
    return {"status": "ok", "version": __version__, "stripe": stripe_key() is not None}


@app.get("/v1/tenant/config")
def tenant_config(tenant: TenantConfig = Depends(get_tenant)):
    return {
        "tenant_id": tenant.tenant_id,
        "name": tenant.name,
        "diesel_price": tenant.diesel_price,
        "is_demo": store.is_demo(tenant.tenant_id),
        "avoid_zones": [z.model_dump() for z in tenant.avoid_zones],
        "toll_plazas": [p.model_dump() for p in tenant.toll_plazas],
    }


@app.get("/v1/vehicles")
def vehicles(tenant: TenantConfig = Depends(get_tenant)):
    fleet = {**DEFAULT_FLEET, **tenant.fleet}
    return {vid: v.model_dump() for vid, v in fleet.items()}


def _require_quota(tenant: TenantConfig, n_routes: int) -> None:
    decision = billing_store.check_and_consume(tenant.tenant_id, n_routes)
    if not decision.allowed:
        raise HTTPException(status_code=402, detail=decision.reason)


@app.post("/v1/routes/compute", response_model=RouteJobResult)
async def compute_route(job: RouteJob, tenant: TenantConfig = Depends(get_tenant)):
    _require_quota(tenant, 1)
    response = await compute_batch([job], tenant)
    result = response.results[0]
    if result.options:
        route_log.log(tenant.tenant_id, job, result.options[0])
    return result


@app.post("/v1/routes/batch", response_model=BatchRouteResponse)
async def compute_routes_batch(
    req: BatchRouteRequest, tenant: TenantConfig = Depends(get_tenant)
):
    if not req.jobs:
        raise HTTPException(status_code=422, detail="lista de jobs vazia")
    if len(req.jobs) > 100:
        raise HTTPException(status_code=422, detail="máximo de 100 jobs por lote")
    _require_quota(tenant, len(req.jobs))
    response = await compute_batch(req.jobs, tenant)
    for job, result in zip(req.jobs, response.results):
        if result.options:
            route_log.log(tenant.tenant_id, job, result.options[0])
    return response


# ---------------------------------------------------------------------------
# Frota, manutenção e dashboard
# ---------------------------------------------------------------------------

@app.get("/v1/fleet")
def fleet(tenant: TenantConfig = Depends(get_tenant)):
    vehicles = vehicle_store.list_with_maintenance(tenant.tenant_id)
    return {"vehicles": vehicles, "summary": fleet_summary(vehicles)}


@app.post("/v1/fleet")
def fleet_add(vehicle: VehicleIn, tenant: TenantConfig = Depends(get_tenant)):
    return vehicle_store.create(tenant.tenant_id, vehicle)


@app.get("/v1/dashboard")
def dashboard(tenant: TenantConfig = Depends(get_tenant)):
    vehicles = vehicle_store.list_with_maintenance(tenant.tenant_id)
    summary = fleet_summary(vehicles)
    sub = billing_store.get_or_create(tenant.tenant_id)
    plan = PLANS.get(sub.plan_id, PLANS["essencial"])
    return {
        "tenant": {"id": tenant.tenant_id, "name": tenant.name,
                   "is_demo": store.is_demo(tenant.tenant_id),
                   "diesel_price": tenant.diesel_price},
        "fleet": summary,
        "routes": route_log.stats(tenant.tenant_id),
        "recent_routes": route_log.recent(tenant.tenant_id, 8),
        "billing": {"plan_id": sub.plan_id, "plan_name": plan.name,
                    "status": sub.status, "routes_used_month": sub.routes_used_month,
                    "routes_per_month": plan.routes_per_month},
    }


# ---------------------------------------------------------------------------
# Agente analítico (chatbot)
# ---------------------------------------------------------------------------

@app.post("/v1/assistant")
def assistant(body: dict, tenant: TenantConfig = Depends(get_tenant)):
    question = (body.get("question") or "").strip()
    return agent.answer(tenant.tenant_id, question)


@app.get("/v1/assistant/suggestions")
def assistant_suggestions(tenant: TenantConfig = Depends(get_tenant)):
    return {"suggestions": AnalyticalAgent.SUGGESTIONS}


# ---------------------------------------------------------------------------
# Pesquisa Operacional — otimização multi-origem/multi-destino
# ---------------------------------------------------------------------------

@app.post("/v1/optimize")
def optimize(body: dict, tenant: TenantConfig = Depends(get_tenant)):
    """Aloca o transporte de N origens (talhões) para M destinos (usinas) ao
    menor custo total (problema de transporte), usando o custo real por km do
    veículo escolhido. Também dimensiona o nº de viagens.
    """
    origins = body.get("origins", [])
    destinations = body.get("destinations", [])
    if not origins or not destinations:
        raise HTTPException(status_code=422, detail="informe origens e destinos")
    if len(origins) * len(destinations) > 400:
        raise HTTPException(status_code=422, detail="máximo de 400 pares origem×destino")
    try:
        vehicle = tenant.vehicle(body.get("vehicle_id", "treminhao"))
    except KeyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # custo por km do veículo (modelo físico: combustível + manutenção)
    from .cost import R0
    pbt = vehicle.tare_t + vehicle.payload_t
    fuel_l_per_km = R0 * pbt
    cost_per_km = fuel_l_per_km * tenant.diesel_price + vehicle.maintenance_rs_km
    payload = max(1.0, vehicle.payload_t)

    supply = [float(o.get("supply", payload)) for o in origins]
    demand = [float(d.get("demand", payload)) for d in destinations]
    # matriz de custo por tonelada = (km * custo/km) / carga útil
    cost = []
    for o in origins:
        row = []
        for d in destinations:
            km = haversine_km(o["lat"], o["lon"], d["lat"], d["lon"])
            row.append(round(km * cost_per_km / payload, 4))
        cost.append(row)

    result = or_opt.solve_transportation(supply, demand, cost)
    if not result["success"]:
        raise HTTPException(status_code=422, detail=result.get("message", "otimização inviável"))

    # traduz o fluxo em plano legível + nº de viagens
    plan = []
    total_trips = 0
    for i, o in enumerate(origins):
        for j, d in enumerate(destinations):
            t = result["flows"][i][j]
            if t > 0.01:
                trips = int(-(-t // payload))  # ceil
                total_trips += trips
                km = haversine_km(o["lat"], o["lon"], d["lat"], d["lon"])
                plan.append({
                    "origin": o.get("name", f"O{i+1}"), "destination": d.get("name", f"D{j+1}"),
                    "tonnes": round(t, 1), "trips": trips, "distance_km": round(km, 1),
                    "cost": round(t * cost[i][j], 2),
                })
    plan.sort(key=lambda p: p["cost"], reverse=True)
    return {
        "vehicle": vehicle.id, "payload_t": payload,
        "total_cost": result["total_cost"], "total_tonnes": result["delivered"],
        "total_trips": total_trips, "unmet_demand_t": result["unmet_demand"],
        "plan": plan,
    }


# ---------------------------------------------------------------------------
# Precificação por uso (calculadora)
# ---------------------------------------------------------------------------

@app.post("/v1/billing/quote")
def billing_quote(req: QuoteRequest):
    return quote(req)


@app.get("/v1/billing/pricing")
def billing_pricing():
    return PRICE


# ---------------------------------------------------------------------------
# Machine Learning
# ---------------------------------------------------------------------------

@app.get("/v1/ml/maintenance-risk")
def ml_maintenance_risk(tenant: TenantConfig = Depends(get_tenant)):
    """Risco (probabilidade) de intervenção por componente, via regressão logística."""
    out = []
    for v in vehicle_store.list_with_maintenance(tenant.tenant_id):
        comps = []
        for p in v["maintenance"]:
            usage = min(1.0, (p["current"] or 0) / (p["limit"] or 1))
            risk = _risk_model.risk_from_component(p["wear_pct"], usage)
            comps.append({"component": p["component"], "label": p["label"],
                          "wear_pct": p["wear_pct"], "risk_pct": round(risk * 100, 0),
                          "risk_label": MaintenanceRiskModel.label(risk)})
        out.append({"plate": v["plate"], "type": v["type"], "components": comps})
    return {"vehicles": out}


@app.get("/v1/ml/demand-forecast")
def ml_demand_forecast(horizon: int = 7, tenant: TenantConfig = Depends(get_tenant)):
    recent = route_log.recent(tenant.tenant_id, 200)
    by_day: dict[str, int] = {}
    for r in recent:
        day = (r.get("created_at") or "")[:10]
        by_day[day] = by_day.get(day, 0) + 1
    series = [by_day[d] for d in sorted(by_day)]
    if len(series) < 2:
        return {"forecast": [], "history": series, "message": "histórico insuficiente"}
    fc = DemandForecaster().fit(series)
    return {"forecast": fc.forecast(min(horizon, 30)), "history": series,
            "trend": "alta" if fc.slope > 0.1 else "baixa" if fc.slope < -0.1 else "estável"}


@app.post("/v1/ml/fuel-calibrate")
def ml_fuel_calibrate(body: dict, tenant: TenantConfig = Depends(get_tenant)):
    """Calibra o modelo de consumo a partir de pares (previsto, real) da telemetria."""
    pairs = body.get("pairs", [])
    if not pairs:
        raise HTTPException(status_code=422, detail="informe pares [previsto, real]")
    pred = [p[0] for p in pairs]
    actual = [p[1] for p in pairs]
    cal = FuelCalibrator().fit(pred, actual)
    return cal.as_dict()


# ---------------------------------------------------------------------------
# Demo pública (Triângulo Mineiro / MG)
# ---------------------------------------------------------------------------

@app.get("/v1/demo/config")
def demo_config():
    """Chave e rota de exemplo para a degustação — sem login."""
    tenant = store.by_id(DEMO_TENANT_ID)
    if not tenant:
        raise HTTPException(status_code=404, detail="demo indisponível")
    return {
        "api_key": tenant.api_key,
        "region": "Triângulo Mineiro (MG)",
        "sample": {
            "origin": {"lat": -19.90, "lon": -48.10, "name": "Talhão canavieiro — Triângulo Mineiro/MG"},
            "dest": {"lat": -19.9707, "lon": -47.7799, "name": "Usina — Delta/MG"},
            "vehicle_id": "rodotrem",
        },
    }


# ---------------------------------------------------------------------------
# Billing — assinatura mensal recorrente
# ---------------------------------------------------------------------------

@app.get("/v1/billing/plans")
def billing_plans():
    return {pid: p.model_dump(exclude={"stripe_price_id"}) for pid, p in public_plans().items()}


@app.get("/v1/billing/status")
def billing_status(tenant: TenantConfig = Depends(get_tenant)):
    sub = billing_store.refresh(tenant.tenant_id)
    plan = PLANS.get(sub.plan_id, PLANS["essencial"])
    return {
        **sub.model_dump(exclude={"provider_sub_id", "stripe_customer_id"}),
        "plan_name": plan.name,
        "routes_per_month": plan.routes_per_month,
        "price_month_brl": plan.price_month_brl,
    }


@app.post("/v1/billing/checkout")
async def billing_checkout(
    body: dict, request: Request, tenant: TenantConfig = Depends(get_tenant)
):
    plan_id = body.get("plan_id", "essencial")
    if plan_id not in PLANS or not PLANS[plan_id].public:
        raise HTTPException(status_code=422, detail="plano desconhecido")
    if plan_id == "enterprise":
        raise HTTPException(status_code=422,
                            detail=f"Enterprise: fale com {CONTACT_EMAIL}")
    base_url = str(request.base_url).rstrip("/")
    async with httpx.AsyncClient() as http_client:
        url = await create_checkout_session(tenant.tenant_id, PLANS[plan_id], base_url, http_client)
    return {"checkout_url": url, "sandbox": stripe_key() is None}


@app.get("/v1/billing/dev/activate", include_in_schema=False)
def billing_dev_activate(plan_id: str = "essencial",
                         tenant: TenantConfig = Depends(get_tenant)):
    """Sandbox de desenvolvimento: ativa a assinatura sem passar pelo Stripe."""
    if stripe_key():
        raise HTTPException(status_code=404, detail="indisponível com Stripe configurado")
    if plan_id not in PLANS or not PLANS[plan_id].public:
        raise HTTPException(status_code=422, detail="plano desconhecido")
    sub = billing_store.activate(tenant.tenant_id, plan_id)
    return {"status": sub.status, "plan_id": sub.plan_id, "period_end": sub.period_end}


@app.post("/v1/billing/webhook", include_in_schema=False)
async def billing_webhook(request: Request):
    """Webhook Stripe com verificação de assinatura (HMAC-SHA256)."""
    raw = await request.body()
    secret = webhook_secret()
    if secret:
        sig = request.headers.get("stripe-signature")
        if not verify_stripe_signature(raw, sig, secret):
            raise HTTPException(status_code=400, detail="assinatura do webhook inválida")
    elif stripe_key():
        # Stripe configurado mas sem secret de webhook: recuse por segurança
        raise HTTPException(status_code=400, detail="STRIPE_WEBHOOK_SECRET não configurado")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="payload inválido")
    return {"result": handle_stripe_event(event, billing_store)}


# ---------------------------------------------------------------------------
# Leads (formulário de contato)
# ---------------------------------------------------------------------------

@app.post("/v1/leads")
def create_lead(lead: LeadIn, request: Request, background: BackgroundTasks):
    ip = client_ip(request)
    if not lead_store.rate.allow(ip):
        raise HTTPException(status_code=429, detail="muitas solicitações — tente em instantes")
    saved = lead_store.create(lead, ip=ip)
    # honeypot (bot) -> resposta 200 silenciosa, sem gravar nem notificar
    if saved:
        # notifica contato@nokahi.com e giselle@coutofalcao.com sem bloquear a resposta
        background.add_task(send_lead_notification, saved)
    return {"ok": True, "id": saved["id"] if saved else None}


@app.get("/v1/admin/leads")
def list_leads(status: str | None = None, _: None = Depends(require_admin)):
    return {"count": lead_store.count(), "leads": lead_store.list(status=status)}


@app.post("/v1/admin/leads/{lead_id}/status")
def update_lead_status(lead_id: int, body: dict, _: None = Depends(require_admin)):
    status = body.get("status", "")
    if status not in ("novo", "contatado", "qualificado", "descartado"):
        raise HTTPException(status_code=422, detail="status inválido")
    if not lead_store.set_status(lead_id, status):
        raise HTTPException(status_code=404, detail="lead não encontrado")
    return {"ok": True}
