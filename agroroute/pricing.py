"""Precificação por uso do NOKAHI AgroRoute.

O custo para o cliente é dimensionado pelos DRIVERS que realmente geram custo de
infraestrutura e operação:
  - nº de veículos monitorados (telemetria, storage, modelos de ML)
  - nº de rotas calculadas/mês (roteamento, elevação, clima, otimização)
  - nº de origens (talhões) e nº de destinos (usinas/pátios) cadastrados

Cada unidade é cobrada com markup >= 5x sobre seu custo variável, garantindo
margem BRUTA >= 80% por unidade (ver BUSINESS_CASE.md). A mensalidade é:

    total = base + veículos·pv + max(0, rotas - incluídas)·pr
                 + origens·po + destinos·pd
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# Preços unitários (BRL). Calibrados p/ margem bruta >= 80%.
PRICE = {
    "base_month": 2900.0,       # plataforma: dashboard, agente analítico, suporte
    "per_vehicle": 160.0,       # por veículo monitorado/mês
    "included_routes": 500,     # rotas inclusas na base
    "per_route": 1.20,          # rota excedente
    "per_origin": 14.0,         # por talhão/origem cadastrada/mês
    "per_destination": 95.0,    # por usina/pátio de destino/mês
}

# Custo variável por unidade (para exibir a margem — não é preço)
UNIT_COST = {
    "platform": 400.0, "per_vehicle": 30.0, "per_route": 0.25,
    "per_origin": 2.5, "per_destination": 18.0,
}


class QuoteRequest(BaseModel):
    vehicles: int = Field(0, ge=0, le=100000)
    routes_per_month: int = Field(0, ge=0, le=10_000_000)
    origins: int = Field(0, ge=0, le=1_000_000)
    destinations: int = Field(0, ge=0, le=100000)


def quote(req: QuoteRequest) -> dict:
    billable_routes = max(0, req.routes_per_month - PRICE["included_routes"])
    items = [
        {"item": "Plataforma (base)", "qty": 1, "unit": PRICE["base_month"],
         "subtotal": PRICE["base_month"]},
        {"item": "Veículos monitorados", "qty": req.vehicles, "unit": PRICE["per_vehicle"],
         "subtotal": req.vehicles * PRICE["per_vehicle"]},
        {"item": f"Rotas excedentes (> {PRICE['included_routes']} inclusas)",
         "qty": billable_routes, "unit": PRICE["per_route"],
         "subtotal": billable_routes * PRICE["per_route"]},
        {"item": "Origens (talhões)", "qty": req.origins, "unit": PRICE["per_origin"],
         "subtotal": req.origins * PRICE["per_origin"]},
        {"item": "Destinos (usinas/pátios)", "qty": req.destinations, "unit": PRICE["per_destination"],
         "subtotal": req.destinations * PRICE["per_destination"]},
    ]
    total = sum(i["subtotal"] for i in items)

    # custo variável estimado e margem bruta
    var_cost = (
        UNIT_COST["platform"]
        + req.vehicles * UNIT_COST["per_vehicle"]
        + req.routes_per_month * UNIT_COST["per_route"]
        + req.origins * UNIT_COST["per_origin"]
        + req.destinations * UNIT_COST["per_destination"]
    )
    gross_margin = (total - var_cost) / total if total > 0 else 0.0
    return {
        "items": [{**i, "subtotal": round(i["subtotal"], 2), "unit": round(i["unit"], 2)}
                  for i in items],
        "monthly_total": round(total, 2),
        "annual_total": round(total * 12, 2),
        "estimated_variable_cost": round(var_cost, 2),
        "gross_margin_pct": round(gross_margin * 100, 1),
        "drivers": req.model_dump(),
    }
