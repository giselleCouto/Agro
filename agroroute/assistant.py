"""Agente analítico (chatbot) ancorado nos dados do tenant.

Responde perguntas em linguagem natural sobre a operação — frota, manutenção,
rotas, economia, custo/plano e otimização — computando as respostas a partir dos
dados reais do tenant (não é texto genérico). Usa os modelos de ML para risco de
manutenção e previsão de demanda.

Determinístico e offline por padrão (classificação de intenção por palavras-chave
+ consulta aos stores). Se `ANTHROPIC_API_KEY` estiver configurada, o método
`answer` pode ser estendido para redigir a resposta com um LLM sobre os mesmos
dados — o gancho está isolado em `_llm_polish` (no-op sem chave).
"""
from __future__ import annotations

import os
import re
import unicodedata

from .fleet import fleet_summary
from .ml import DemandForecaster, MaintenanceRiskModel

_risk_model = MaintenanceRiskModel()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def _any(text: str, *words: str) -> bool:
    return any(w in text for w in words)


class AnalyticalAgent:
    def __init__(self, vehicle_store, route_log, billing_store, plans):
        self.vehicles = vehicle_store
        self.routes = route_log
        self.billing = billing_store
        self.plans = plans

    # -- capacidades expostas ao usuário --
    SUGGESTIONS = [
        "Quantos caminhões precisam de manutenção?",
        "Qual a economia das minhas rotas?",
        "Qual componente tem maior risco de falha?",
        "Qual a previsão de demanda de rotas?",
        "Quanto estou pagando e qual meu uso?",
        "Como otimizar várias rotas de uma vez?",
    ]

    def answer(self, tenant_id: str, question: str) -> dict:
        q = _norm(question)
        if not q:
            return self._help()

        if _any(q, "ajuda", "o que voce faz", "help", "pode fazer", "comandos"):
            return self._help()
        if _any(q, "manuten", "desgaste", "pneu", "freio", "suspens", "motor", "risco", "falha"):
            return self._maintenance(tenant_id, q)
        if _any(q, "frota", "caminho", "veicul", "quantos carros", "operante"):
            return self._fleet(tenant_id)
        if _any(q, "previs", "demanda", "forecast", "proximos dias", "tendenc"):
            return self._demand(tenant_id)
        if _any(q, "otimiz", "alocar", "aloca", "varias rotas", "multi", "origem", "destino"):
            return self._optimize_help()
        if _any(q, "plano", "assinatura", "cobranc", "preco", "pagar", "pago", "cota", "custo do plano"):
            return self._billing(tenant_id)
        if _any(q, "rota", "economia", "consumo", "custo", "combustivel", "pedagio", "diesel"):
            return self._routes(tenant_id)
        return self._fallback()

    # -- intents --
    def _fleet(self, tid: str) -> dict:
        vs = self.vehicles.list_with_maintenance(tid)
        s = fleet_summary(vs)
        txt = (f"Sua frota tem **{s['total']} veículo(s)**: "
               f"{s['by_status'].get('active',0)} operante(s), "
               f"{s['by_status'].get('maintenance',0)} em manutenção. "
               f"**{s['needs_maintenance']}** precisam de manutenção imediata "
               f"(crítico/alto).")
        return {"answer": txt, "data": {"summary": s}}

    def _maintenance(self, tid: str, q: str) -> dict:
        vs = self.vehicles.list_with_maintenance(tid)
        alerts = fleet_summary(vs)["alerts"]
        # enriquece com risco de ML (probabilidade de intervenção)
        for a in alerts:
            usage = min(1.0, (a["current"] or 0) / (a["limit"] or 1))
            a["ml_risk"] = round(_risk_model.risk_from_component(a["wear_pct"], usage) * 100, 0)
        alerts.sort(key=lambda a: a["ml_risk"], reverse=True)
        if not alerts:
            return {"answer": "✅ Nenhum componente precisa de manutenção imediata — frota em ordem.",
                    "data": {"alerts": []}}
        top = alerts[0]
        crit = sum(1 for a in alerts if a["severity"] == "critical")
        txt = (f"**{len(alerts)} alerta(s)** de manutenção ({crit} crítico(s)). "
               f"Maior risco: **{top['plate']} — {top['label']}** "
               f"({top['wear_pct']:.0f}% de desgaste, risco ML {top['ml_risk']:.0f}%). "
               f"Recomendo priorizar a inspeção deste componente.")
        return {"answer": txt, "data": {"alerts": alerts[:6]}}

    def _routes(self, tid: str) -> dict:
        st = self.routes.stats(tid)
        recent = self.routes.recent(tid, 20)
        if st["routes"] == 0:
            return {"answer": "Você ainda não calculou rotas. Vá em **Rotas** e informe origem→destino "
                              "para ver 4 alternativas com o custo real.", "data": {}}
        avg = st["total_cost"] / st["routes"]
        cheapest = min(recent, key=lambda r: r["total_cost"]) if recent else None
        priciest = max(recent, key=lambda r: r["total_cost"]) if recent else None
        spread = (priciest["total_cost"] - cheapest["total_cost"]) if cheapest and priciest else 0
        txt = (f"Você calculou **{st['routes']} rota(s)**, somando {st['total_km']:.0f} km e "
               f"R$ {st['total_cost']:.0f} em custo estimado (média R$ {avg:.0f}/rota). "
               f"A diferença entre a rota mais cara e a mais barata recentes é de **R$ {spread:.0f}** — "
               f"escolher a melhor rota é onde está a economia.")
        return {"answer": txt, "data": {"stats": st}}

    def _demand(self, tid: str) -> dict:
        recent = self.routes.recent(tid, 200)
        if len(recent) < 4:
            return {"answer": "Ainda não há histórico suficiente para prever a demanda. "
                              "Após alguns dias calculando rotas, a previsão fica disponível.", "data": {}}
        # série diária de nº de rotas
        by_day: dict[str, int] = {}
        for r in recent:
            day = (r.get("created_at") or "")[:10]
            by_day[day] = by_day.get(day, 0) + 1
        series = [by_day[d] for d in sorted(by_day)]
        fc = DemandForecaster().fit(series)
        forecast = fc.forecast(7)
        txt = (f"Com base em {len(series)} dia(s) de operação, a previsão de rotas para os próximos "
               f"7 dias é ~**{sum(forecast)/len(forecast):.0f}/dia** "
               f"(tendência {'de alta' if fc.slope > 0.1 else 'de baixa' if fc.slope < -0.1 else 'estável'}). "
               f"Use isso para dimensionar frota e turnos na safra.")
        return {"answer": txt, "data": {"forecast": forecast, "history": series}}

    def _billing(self, tid: str) -> dict:
        sub = self.billing.refresh(tid)
        plan = self.plans.get(sub.plan_id)
        name = plan.name if plan else sub.plan_id
        quota = plan.routes_per_month if plan else 0
        txt = (f"Seu plano é **{name}** (status: {sub.status}). "
               f"Uso este mês: **{sub.routes_used_month}/{quota if quota < 1e8 else '∞'}** rotas. "
               f"O custo real é dimensionado por veículos, rotas, origens e destinos — "
               f"use a calculadora de preço para simular.")
        return {"answer": txt, "data": {"plan_id": sub.plan_id, "used": sub.routes_used_month,
                                        "quota": quota}}

    def _optimize_help(self) -> dict:
        return {"answer": "Para **otimizar várias rotas de uma vez** (multi-origem/multi-destino), use o "
                          "endpoint de otimização: informe os talhões (origens) com volume, as usinas "
                          "(destinos) com capacidade e a frota. A NOKAHI resolve o **problema de transporte** "
                          "(quanto enviar de cada talhão para cada usina ao menor custo) e a **atribuição** "
                          "das viagens aos veículos. É pesquisa operacional sobre o custo real de cada rota.",
                "data": {"endpoint": "/v1/optimize"}}

    def _help(self) -> dict:
        return {"answer": "Sou o assistente analítico da NOKAHI. Posso responder sobre sua frota, "
                          "manutenção (com risco por ML), rotas e economia, previsão de demanda, seu "
                          "plano/uso e como otimizar várias rotas. Pergunte à vontade.",
                "data": {"suggestions": self.SUGGESTIONS}}

    def _fallback(self) -> dict:
        return {"answer": "Não entendi bem. Posso ajudar com **frota**, **manutenção**, **rotas/economia**, "
                          "**previsão de demanda**, **plano/uso** ou **otimização** de rotas. "
                          "Tente reformular ou toque numa sugestão.",
                "data": {"suggestions": self.SUGGESTIONS}}

    def _llm_polish(self, text: str) -> str:  # pragma: no cover - gancho opcional
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return text
        return text  # ponto de extensão: redigir com Claude sobre os mesmos dados
