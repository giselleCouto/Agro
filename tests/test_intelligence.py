"""Testes dos módulos de inteligência de frota."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import intelligence as intel
from agroroute.api import app

client = TestClient(app)
DEMO = {"X-API-Key": "demo-mg-2026"}


def test_frota_deterministica():
    a = intel.gerar_frota_telemetria("t1", 50)
    b = intel.gerar_frota_telemetria("t1", 50)
    c = intel.gerar_frota_telemetria("t2", 50)
    assert [v["placa"] for v in a] == [v["placa"] for v in b]      # estável
    assert [v["risco_falha_estimado"] for v in a] != [v["risco_falha_estimado"] for v in c]
    assert len(a) == 50


def test_kpis_manutencao_validos():
    frota = intel.gerar_frota_telemetria("t1", 200)
    k = intel.kpis_manutencao(frota)
    assert 0 <= k["disponibilidade"] <= 100
    assert k["mtbf"] > 0 and k["mttr"] >= 0
    assert 0 <= k["percentualCorretiva"] <= 100
    assert k["custoTotalParadas"] >= 0


def test_kpis_telemetria():
    frota = intel.gerar_frota_telemetria("t1", 200)
    k = intel.kpis_telemetria(frota)
    for key in ("media_score_conducao", "media_eficiencia", "operadores_agressivos",
                "media_variacao_consumo", "total_alertas_sobrecarga", "media_custo_hora"):
        assert key in k


def test_alertas_inteligentes_severidade():
    frota = intel.gerar_frota_telemetria("t1", 300)
    A = intel.alertas_inteligentes(frota)
    assert A, "esperava alertas numa frota de 300"
    assert all(a["severidade"] in ("alta", "media") for a in A)
    # ordenados: críticos antes
    sev = [a["severidade"] for a in A]
    assert sev == sorted(sev, key=lambda s: 0 if s == "alta" else 1)


def test_alertas_preditivos_buckets():
    frota = intel.gerar_frota_telemetria("t1", 300)
    p = intel.alertas_preditivos(frota)
    assert p["criticos"] >= 0 and p["altos"] >= 0 and p["medios"] >= 0
    assert all(a["probabilidade_falha"] > 40 for a in p["alertas"])


def test_previsoes_ordenadas_por_urgencia():
    frota = intel.gerar_frota_telemetria("t1", 100)
    prev = intel.previsoes_preventivas(frota)
    dias = [p["dias_ate_intervencao"] for p in prev]
    assert dias == sorted(dias)
    assert all(1 <= d <= 90 for d in dias)


def test_avaliacao_desempenho_scores():
    av = intel.avaliacao_desempenho()
    assert len(av["mecanicos"]) == 4 and len(av["fornecedores"]) == 3
    scores = [m["score"] for m in av["mecanicos"]]
    assert scores == sorted(scores, reverse=True)   # ranking
    assert all(0 <= s <= 10 for s in scores)


def test_overview_endpoint():
    r = client.get("/v1/intel/overview?n=200", headers=DEMO)
    assert r.status_code == 200
    d = r.json()
    for key in ("kpis_manutencao", "kpis_telemetria", "alertas_inteligentes",
                "alertas_preditivos", "cronograma", "periodos_criticos", "heatmap",
                "impacto_financeiro", "avaliacao"):
        assert key in d
    assert len(d["periodos_criticos"]) == 3


def test_overview_requires_auth():
    assert client.get("/v1/intel/overview").status_code in (401, 422)
