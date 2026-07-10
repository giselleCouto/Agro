"""Módulos de inteligência de frota — KPIs, telemetria, alertas e manutenção
preditiva/preventiva, calculados de verdade (não mock) e ligados aos modelos
de ML.

Porta a inteligência do dashboard v8 (ManutençãoFrota, ManutençãoPreventiva,
Telemetria, PeríodosCríticos, MapaOperacional, AvaliaçãoDesempenho) para o
backend, gerando a frota de telemetria de forma DETERMINÍSTICA (semeada por
tenant) para que os números sejam estáveis entre chamadas.
"""
from __future__ import annotations

import hashlib
import random

from .ml import DemandForecaster, MaintenanceRiskModel

_risk = MaintenanceRiskModel()

FRENTES = ["Frente 1", "Frente 2", "Frente 3", "Frente 4"]
TIPOS = ["Caminhão", "Colhedora", "Trator"]
TURNOS = ["A", "B", "C"]
MODELOS = {
    "Caminhão": ["Scania R450", "Volvo FH540", "Mercedes Actros", "Iveco Hi-Way"],
    "Colhedora": ["John Deere CH570", "Case A8800", "Valtra BC7500"],
    "Trator": ["John Deere 8R", "Massey 8737", "Valtra T250"],
}
NOMES = [
    "João Silva", "Pedro Santos", "Carlos Oliveira", "Rafael Lima", "Marcos Souza",
    "André Costa", "Bruno Alves", "Diego Rocha", "Felipe Dias", "Gustavo Melo",
    "Henrique Nunes", "Igor Ramos", "Lucas Ferreira", "Mateus Barros", "Thiago Gomes",
]


def _rng(seed: str) -> random.Random:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:12], 16)
    return random.Random(h)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Geração determinística da frota de telemetria
# ---------------------------------------------------------------------------

def gerar_frota_telemetria(tenant_id: str, n: int = 340) -> list[dict]:
    out = []
    for i in range(n):
        r = _rng(f"{tenant_id}:{i}")
        tipo = TIPOS[i % 3]
        frente = FRENTES[i % 4]
        turno = TURNOS[i % 3]
        modelo = r.choice(MODELOS[tipo])
        placa = f"{chr(65 + i % 26)}{chr(65 + (i // 26) % 26)}{chr(65 + (i // 7) % 26)}-{1000 + i % 9000}"
        operador = r.choice(NOMES)

        wear = _clamp(r.gauss(55, 25), 5, 99)                # desgaste %
        score = _clamp(r.gauss(72, 17), 22, 99)              # score de condução
        consumo_esperado = r.uniform(28, 42)
        variacao = _clamp(r.gauss(6, 9), -6, 30)             # % acima do esperado
        consumo_medio = consumo_esperado * (1 + variacao / 100)
        frenamentos = int(_clamp(r.gauss(10, 7), 0, 35))
        temperatura = _clamp(r.gauss(92, 6), 80, 110)
        tempo_ocioso = _clamp(r.gauss(1.4, 1.0), 0.1, 4.5)
        eficiencia = _clamp(r.gauss(68, 15), 28, 98)
        horas_operacao = r.uniform(380, 720)
        custo_hora = r.uniform(120, 260)
        impacto_ociosidade = tempo_ocioso * custo_hora * 0.35

        # risco de falha via modelo de ML (logística) — âncora no desgaste,
        # com contribuição de temperatura e conduta
        terrain = _clamp((temperatura - 85) / 25, 0, 1)
        load = _clamp(1 - eficiencia / 100 + variacao / 60, 0, 1)
        risco = _risk.risk_from_component(wear, wear / 100, terrain, load) * 100
        num_falhas = int(_clamp(round(risco / 14 + r.uniform(-1, 1)), 0, 9))
        tempo_reparo = num_falhas * r.uniform(1.5, 4.5)
        custo_parada = num_falhas * r.uniform(1800, 6500)
        tipo_ult_manut = ["preventiva", "preditiva", "corretiva"][
            0 if risco < 40 else 1 if risco < 70 else 2
        ]
        status = "manutencao" if risco > 88 else ("inativo" if r.random() < 0.02 else "active")

        out.append({
            "id": f"{tenant_id}-v{i}", "placa": placa, "tipo": tipo, "modelo": modelo,
            "frente": frente, "turno": turno, "status": status,
            "wear_pct": round(wear, 1), "operador": operador,
            "score_conducao": round(score, 0), "consumo_esperado": round(consumo_esperado, 1),
            "consumo_medio": round(consumo_medio, 1), "variacao_consumo": round(variacao, 1),
            "frenamentos_bruscos": frenamentos, "temperatura_motor": round(temperatura, 0),
            "tempo_ocioso": round(tempo_ocioso, 1), "eficiencia_operacional": round(eficiencia, 0),
            "custo_hora": round(custo_hora, 0), "impacto_ociosidade": round(impacto_ociosidade, 0),
            "risco_falha_estimado": round(risco, 0), "probabilidade_falha": round(risco, 0),
            "score_risco": round(risco, 0), "numero_falhas": num_falhas,
            "horas_operacao": round(horas_operacao, 0), "tempo_reparo": round(tempo_reparo, 1),
            "custo_parada": round(custo_parada, 0), "tipo_ultima_manutencao": tipo_ult_manut,
        })
    return out


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def kpis_manutencao(frota: list[dict]) -> dict:
    n = len(frota) or 1
    total_horas = sum(v["horas_operacao"] for v in frota)
    total_falhas = sum(v["numero_falhas"] for v in frota)
    total_reparo = sum(v["tempo_reparo"] for v in frota)
    reparos = sum(1 for v in frota if v["numero_falhas"] > 0) or 1
    corretivas = sum(1 for v in frota if v["tipo_ultima_manutencao"] == "corretiva")
    preventivas = sum(1 for v in frota if v["tipo_ultima_manutencao"] != "corretiva")
    em_manut = sum(1 for v in frota if v["status"] == "manutencao")
    custo_paradas = sum(v["custo_parada"] for v in frota
                        if v["tipo_ultima_manutencao"] == "corretiva")
    disponibilidade = 100.0 * (1 - em_manut / n) - (total_reparo / max(total_horas, 1)) * 100 * 0.1
    return {
        "disponibilidade": round(_clamp(disponibilidade, 0, 100), 1),
        "mtbf": round(total_horas / max(total_falhas, 1), 1),
        "mttr": round(total_reparo / reparos, 1),
        "percentualCorretiva": round(100 * corretivas / max(corretivas + preventivas, 1), 1),
        "custoTotalParadas": round(custo_paradas, 0),
        "emManutencao": em_manut, "totalVeiculos": n,
    }


def kpis_telemetria(frota: list[dict]) -> dict:
    n = len(frota) or 1
    return {
        "media_score_conducao": round(sum(v["score_conducao"] for v in frota) / n, 0),
        "media_eficiencia": round(sum(v["eficiencia_operacional"] for v in frota) / n, 0),
        "operadores_agressivos": sum(1 for v in frota
                                     if v["score_conducao"] < 55 or v["frenamentos_bruscos"] > 20),
        "media_variacao_consumo": round(sum(v["variacao_consumo"] for v in frota) / n, 1),
        "total_alertas_sobrecarga": sum(1 for v in frota if v["variacao_consumo"] > 18),
        "media_custo_hora": round(sum(v["custo_hora"] for v in frota) / n, 0),
    }


# ---------------------------------------------------------------------------
# Alertas inteligentes (regras do dashboard v8, com os mesmos limiares)
# ---------------------------------------------------------------------------

def alertas_inteligentes(frota: list[dict]) -> list[dict]:
    A = []
    for v in frota:
        base = {"placa": v["placa"], "modelo": v["modelo"], "frente": v["frente"],
                "operador": v["operador"]}
        if v["variacao_consumo"] > 14:
            A.append({**base, "id": f"{v['id']}-consumo", "tipo": "consumo_elevado",
                      "msg": f"Consumo {v['variacao_consumo']:.0f}% acima do esperado "
                             f"({v['consumo_medio']:.1f} vs {v['consumo_esperado']:.1f} L/h)",
                      "severidade": "alta" if v["variacao_consumo"] > 22 else "media"})
        if v["frenamentos_bruscos"] > 18:
            A.append({**base, "id": f"{v['id']}-frenagem", "tipo": "frenagem_brusca",
                      "msg": f"{v['frenamentos_bruscos']} frenagens bruscas hoje. Risco de "
                             f"desgaste prematuro dos freios.", "severidade": "alta"})
        if v["score_conducao"] < 50:
            A.append({**base, "id": f"{v['id']}-score", "tipo": "score_critico",
                      "msg": f"Score de condução crítico: {v['score_conducao']:.0f}/100. "
                             f"Treinamento urgente recomendado.", "severidade": "alta"})
        if v["temperatura_motor"] > 103:
            A.append({**base, "id": f"{v['id']}-temp", "tipo": "temperatura_critica",
                      "msg": f"Motor a {v['temperatura_motor']:.0f}°C. Risco de falha "
                             f"iminente elevado.", "severidade": "alta"})
        if v["risco_falha_estimado"] > 78:
            A.append({**base, "id": f"{v['id']}-risco", "tipo": "risco_falha",
                      "msg": f"Probabilidade de falha: {v['risco_falha_estimado']:.0f}%. "
                             f"Inspecionar imediatamente.", "severidade": "alta"})
        if v["tempo_ocioso"] > 2.5:
            A.append({**base, "id": f"{v['id']}-ocioso", "tipo": "marcha_lenta",
                      "msg": f"{v['tempo_ocioso']:.1f}h em marcha lenta. Impacto: "
                             f"R$ {v['impacto_ociosidade']:.0f} desnecessário.", "severidade": "media"})
        if v["eficiencia_operacional"] < 52:
            A.append({**base, "id": f"{v['id']}-efic", "tipo": "baixa_eficiencia",
                      "msg": f"Eficiência operacional: {v['eficiencia_operacional']:.0f}%. "
                             f"Abaixo da média da frota.", "severidade": "media"})
    A.sort(key=lambda a: 0 if a["severidade"] == "alta" else 1)
    return A


def alertas_preditivos(frota: list[dict]) -> dict:
    def nivel(p):
        return "critico" if p > 80 else "alto" if p > 60 else "medio" if p > 40 else "baixo"

    def recomendacao(p):
        if p > 80:
            return "Intervenção imediata necessária"
        if p > 60:
            return "Agendar manutenção nas próximas 48h"
        if p > 40:
            return "Monitorar e agendar na próxima semana"
        return "Manutenção preventiva de rotina"

    alertas = [{"placa": v["placa"], "tipo": v["tipo"], "modelo": v["modelo"],
                "probabilidade_falha": v["probabilidade_falha"], "score_risco": v["score_risco"],
                "numero_falhas": v["numero_falhas"], "nivel": nivel(v["probabilidade_falha"]),
                "recomendacao": recomendacao(v["probabilidade_falha"])}
               for v in frota if v["probabilidade_falha"] > 40]
    alertas.sort(key=lambda a: a["probabilidade_falha"], reverse=True)
    return {
        "criticos": sum(1 for a in alertas if a["nivel"] == "critico"),
        "altos": sum(1 for a in alertas if a["nivel"] == "alto"),
        "medios": sum(1 for a in alertas if a["nivel"] == "medio"),
        "alertas": alertas[:20],
    }


# ---------------------------------------------------------------------------
# Manutenção preventiva — previsão de falha e cronograma
# ---------------------------------------------------------------------------

def previsoes_preventivas(frota: list[dict]) -> list[dict]:
    prev = []
    for v in frota:
        p = v["probabilidade_falha"]
        # dias até intervenção recomendada — quanto maior o risco, mais cedo
        dias = int(_clamp(round((100 - p) / 2.2), 1, 90))
        prev.append({
            "placa": v["placa"], "tipo": v["tipo"], "frente": v["frente"],
            "probabilidade_falha": p, "dias_ate_intervencao": dias,
            "componente_critico": ("Motor" if v["temperatura_motor"] > 100 else
                                   "Freios" if v["frenamentos_bruscos"] > 18 else
                                   "Transmissão" if p > 70 else "Revisão geral"),
            "prioridade": "urgente" if p > 80 else "alta" if p > 60 else
                          "media" if p > 40 else "baixa",
            "custo_estimado": round(v["custo_parada"] * 0.4 + 1500, 0),
        })
    prev.sort(key=lambda x: (x["dias_ate_intervencao"], -x["probabilidade_falha"]))
    return prev


def previsao_kpis(previsoes: list[dict]) -> dict:
    n = len(previsoes) or 1
    urgentes = sum(1 for p in previsoes if p["prioridade"] == "urgente")
    prox7 = sum(1 for p in previsoes if p["dias_ate_intervencao"] <= 7)
    return {
        "total_veiculos": len(previsoes),
        "intervencoes_urgentes": urgentes,
        "proximos_7_dias": prox7,
        "custo_previsto": round(sum(p["custo_estimado"] for p in previsoes
                                    if p["dias_ate_intervencao"] <= 30), 0),
        "risco_medio": round(sum(p["probabilidade_falha"] for p in previsoes) / n, 0),
    }


# ---------------------------------------------------------------------------
# Períodos críticos, heatmap operacional, falhas por hora
# ---------------------------------------------------------------------------

def periodos_criticos(frota: list[dict]) -> list[dict]:
    defs = [
        {"id": "pre-almoco", "nome": "Pré-Almoço", "horario": "10h–12h", "cor": "amber"},
        {"id": "troca-turno", "nome": "Troca de Turno", "horario": "14h–16h", "cor": "red"},
        {"id": "final-dia", "nome": "Final do Dia", "horario": "20h–22h", "cor": "purple"},
    ]
    out = []
    for k, d in enumerate(defs):
        sub = [v for i, v in enumerate(frota) if i % 3 == k]
        total = len(sub) or 1
        irregulares = sum(1 for v in sub if v["eficiencia_operacional"] < 60
                          or v["frenamentos_bruscos"] > 15)
        perda = sum(v["impacto_ociosidade"] for v in sub)
        top = sorted(sub, key=lambda v: v["frenamentos_bruscos"], reverse=True)[:10]
        out.append({
            **d, "totalCiclos": total, "totalIrregulares": irregulares,
            "percentual": round(100 * irregulares / total, 1), "perda": round(perda, 2),
            "top10": [{"placa": v["placa"], "operador": v["operador"], "frente": v["frente"],
                       "turno": v["turno"], "percentual": round(v["frenamentos_bruscos"] * 3, 1),
                       "irregulares": v["frenamentos_bruscos"]} for v in top],
        })
    return out


def heatmap_operacional(frota: list[dict]) -> list[dict]:
    areas = {}
    for v in frota:
        a = areas.setdefault(v["frente"], {"nome": v["frente"], "total_falhas": 0,
                                           "custo_paradas": 0, "tempo_parado": 0,
                                           "horas_trabalhadas": 0, "veiculos": 0})
        a["total_falhas"] += v["numero_falhas"]
        a["custo_paradas"] += v["custo_parada"]
        a["tempo_parado"] += v["tempo_reparo"]
        a["horas_trabalhadas"] += v["horas_operacao"]
        a["veiculos"] += 1
    out = []
    for a in areas.values():
        idx = a["total_falhas"] / max(a["horas_trabalhadas"], 1)
        a["nivel_risco"] = "alto" if idx > 0.012 else "medio" if idx > 0.006 else "baixo"
        a["indice_quebra"] = round(idx, 4)
        a["custo_paradas"] = round(a["custo_paradas"], 0)
        a["tempo_parado"] = round(a["tempo_parado"], 1)
        a["horas_trabalhadas"] = round(a["horas_trabalhadas"], 0)
        out.append(a)
    return sorted(out, key=lambda x: x["indice_quebra"], reverse=True)


def falhas_por_hora(frota: list[dict]) -> list[dict]:
    horas = [0] * 24
    for v in frota:
        r = _rng(v["id"] + "h")
        for _ in range(v["numero_falhas"]):
            # picos em pré-almoço, troca de turno e final do dia
            h = r.choice([10, 11, 14, 15, 20, 21] + list(range(6, 22)))
            horas[h] += 1
    return [{"hora": f"{h:02d}h", "falhas": horas[h]} for h in range(24)]


def impacto_financeiro(frota: list[dict]) -> dict:
    ociosidade = sum(v["impacto_ociosidade"] for v in frota)
    consumo_extra = sum(max(0, v["variacao_consumo"]) / 100 * v["consumo_esperado"]
                        * v["custo_hora"] / 40 * v["horas_operacao"] for v in frota)
    manut_extra = sum(v["custo_parada"] for v in frota
                      if v["score_conducao"] < 60) * 0.3
    total = ociosidade + consumo_extra + manut_extra
    return {
        "total_mensal": round(total, 0),
        "ociosidade": round(ociosidade, 0),
        "consumo_extra": round(consumo_extra, 0),
        "manutencao_extra": round(manut_extra, 0),
        "economia_potencial": round(total * 0.6, 0),
    }


# ---------------------------------------------------------------------------
# Avaliação de mecânicos e fornecedores (scoring do dashboard v8)
# ---------------------------------------------------------------------------

MECANICOS = [
    {"nome": "João Silva", "especialidade": "Motor & Transmissão", "os_concluidas": 87,
     "tempo_medio_h": 3.2, "custo_medio": 3800, "retrabalhos": 2, "satisfacao": 9.4, "anos_exp": 8},
    {"nome": "Pedro Santos", "especialidade": "Freios & Suspensão", "os_concluidas": 74,
     "tempo_medio_h": 4.1, "custo_medio": 3200, "retrabalhos": 4, "satisfacao": 8.7, "anos_exp": 5},
    {"nome": "Carlos Oliveira", "especialidade": "Sistema Elétrico", "os_concluidas": 62,
     "tempo_medio_h": 2.8, "custo_medio": 2900, "retrabalhos": 1, "satisfacao": 9.7, "anos_exp": 12},
    {"nome": "Rafael Lima", "especialidade": "Geral", "os_concluidas": 55,
     "tempo_medio_h": 5.3, "custo_medio": 4500, "retrabalhos": 7, "satisfacao": 7.9, "anos_exp": 3},
]
FORNECEDORES = [
    {"nome": "AutoPeças BR", "categorias": ["Motor", "Filtros"], "pedidos": 48,
     "prazo_medio_dias": 3.2, "prazo_acordado_dias": 4, "custo_medio": 18500,
     "qualidade_score": 9.2, "devolucoes": 1, "desconto_medio": 8.5},
    {"nome": "MecaParts", "categorias": ["Freios", "Pneus", "Suspensão"], "pedidos": 36,
     "prazo_medio_dias": 5.8, "prazo_acordado_dias": 5, "custo_medio": 22000,
     "qualidade_score": 7.8, "devolucoes": 5, "desconto_medio": 5.2},
    {"nome": "AgriSupply", "categorias": ["Transmissão", "Elétrico"], "pedidos": 29,
     "prazo_medio_dias": 4.1, "prazo_acordado_dias": 6, "custo_medio": 31000,
     "qualidade_score": 8.9, "devolucoes": 2, "desconto_medio": 11.0},
]


def _score_mecanico(m: dict) -> float:
    vel = max(0, 10 - (m["tempo_medio_h"] - 2) * 1.5)
    custo = max(0, 10 - (m["custo_medio"] - 2000) / 600)
    retrab = max(0, 10 - m["retrabalhos"] * 1.2)
    return round((vel + custo + retrab + m["satisfacao"]) / 4, 1)


def _score_fornecedor(f: dict) -> float:
    pontual = 10 if f["prazo_medio_dias"] <= f["prazo_acordado_dias"] else \
        max(0, 10 - (f["prazo_medio_dias"] - f["prazo_acordado_dias"]) * 2)
    return round((pontual + f["qualidade_score"] + min(10, f["desconto_medio"])) / 3, 1)


def avaliacao_desempenho() -> dict:
    mec = sorted(({**m, "score": _score_mecanico(m),
                   "classificacao": "Elite" if _score_mecanico(m) >= 8.5 else
                   "Sênior" if _score_mecanico(m) >= 7 else "Em Desenvolvimento"}
                  for m in MECANICOS), key=lambda x: x["score"], reverse=True)
    forn = sorted(({**f, "score": _score_fornecedor(f),
                    "status": "Parceiro Preferencial" if _score_fornecedor(f) >= 8.5 else
                    "Aprovado" if _score_fornecedor(f) >= 7 else "Em Avaliação"}
                   for f in FORNECEDORES), key=lambda x: x["score"], reverse=True)
    return {"mecanicos": mec, "fornecedores": forn}


# ---------------------------------------------------------------------------
# Agregador para o dashboard de inteligência
# ---------------------------------------------------------------------------

def fleet_from_ingest(records: list[dict], alarm_counts: dict[str, int]) -> list[dict]:
    """Monta a frota de inteligência a partir da telemetria REAL ingerida
    (último registro por equipamento + contagem de alarmes)."""
    out = []
    for i, r in enumerate(records):
        eq = r.get("equipment_id") or f"eq{i}"
        alarmes = alarm_counts.get(eq, 0)
        engine_h = r.get("engine_hours") or 0
        temp = r.get("engine_temp")
        temperatura = temp if (temp and temp > 0) else 92
        cons = r.get("fuel_consumption")
        consumo_medio = cons if (cons and cons > 0) else 34.0
        consumo_esperado = 34.0
        variacao = _clamp((consumo_medio / consumo_esperado - 1) * 100, -6, 40)
        score = _clamp(100 - alarmes * 4, 22, 99)
        frenamentos = int(_clamp(alarmes * 1.4, 0, 35))
        eficiencia = _clamp(90 - alarmes * 2.5, 28, 98)
        tempo_ocioso = _clamp(0.5 + alarmes * 0.12, 0.1, 4.5)
        wear = _clamp((engine_h / 100.0) + alarmes * 3, 5, 99) if engine_h else _clamp(alarmes * 6, 5, 99)
        terrain = _clamp((temperatura - 85) / 25, 0, 1)
        load = _clamp(1 - eficiencia / 100 + variacao / 60, 0, 1)
        risco = _risk.risk_from_component(wear, wear / 100, terrain, load) * 100
        custo_hora = 160.0
        out.append({
            "id": eq, "placa": eq, "tipo": r.get("equipment_type") or "Equipamento",
            "modelo": r.get("model") or "—", "frente": r.get("frente") or "—",
            "turno": "A", "status": "manutencao" if risco > 88 else "active",
            "wear_pct": round(wear, 1), "operador": r.get("operator_name") or "—",
            "score_conducao": round(score, 0), "consumo_esperado": round(consumo_esperado, 1),
            "consumo_medio": round(consumo_medio, 1), "variacao_consumo": round(variacao, 1),
            "frenamentos_bruscos": frenamentos, "temperatura_motor": round(temperatura, 0),
            "tempo_ocioso": round(tempo_ocioso, 1), "eficiencia_operacional": round(eficiencia, 0),
            "custo_hora": custo_hora, "impacto_ociosidade": round(tempo_ocioso * custo_hora * 0.35, 0),
            "risco_falha_estimado": round(risco, 0), "probabilidade_falha": round(risco, 0),
            "score_risco": round(risco, 0), "numero_falhas": min(alarmes, 9),
            "horas_operacao": round(engine_h or 500, 0), "tempo_reparo": round(min(alarmes, 9) * 3, 1),
            "custo_parada": round(min(alarmes, 9) * 3500, 0),
            "tipo_ultima_manutencao": "corretiva" if risco > 70 else "preditiva" if risco > 40 else "preventiva",
        })
    return out


def build_overview(frota: list[dict], fonte: str) -> dict:
    prev = previsoes_preventivas(frota)
    return {
        "fonte": fonte,
        "kpis_manutencao": kpis_manutencao(frota),
        "kpis_telemetria": kpis_telemetria(frota),
        "alertas_inteligentes": alertas_inteligentes(frota)[:12],
        "alertas_preditivos": alertas_preditivos(frota),
        "previsao_kpis": previsao_kpis(prev),
        "cronograma": prev[:15],
        "periodos_criticos": periodos_criticos(frota),
        "heatmap": heatmap_operacional(frota),
        "falhas_por_hora": falhas_por_hora(frota),
        "impacto_financeiro": impacto_financeiro(frota),
        "avaliacao": avaliacao_desempenho(),
        "top_telemetria": sorted(frota, key=lambda v: v["risco_falha_estimado"],
                                 reverse=True)[:12],
    }


def intelligence_overview(tenant_id: str, n: int = 340) -> dict:
    """Painel simulado (demo) — sem telemetria real ingerida."""
    return build_overview(gerar_frota_telemetria(tenant_id, n), "simulado")
