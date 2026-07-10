"""Dados fictícios (mas realistas) para a demonstração ter materialidade.

Popula o tenant de demonstração com:
  - histórico de rotas calculadas (dá corpo ao Dashboard e ao assistente)
  - telemetria estilo Solinftec de ~140 equipamentos + alarmes (Integrações
    com dados reais e Inteligência computada sobre a operação ingerida)

Determinístico (semeado por tenant) e idempotente (só semeia se estiver vazio).
Não consome a cota de rotas do lead — o histórico é gravado direto.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta

FRENTES = ["Frente 01", "Frente 02", "Frente 03", "Frente 04", "Frente 05"]
EQUIP = [
    ("Colhedora", ["John Deere CH570", "Case A8800", "Valtra BC7500"]),
    ("Transbordo", ["John Deere 7230J", "Case Magnum 340", "Valtra T250"]),
    ("Caminhão", ["Volvo FH540", "Scania R450", "Mercedes Actros 2651"]),
]
OPERADORES = [
    "Fabrício Souza", "Everton Maciel", "Wellington Alencar", "Roberto Pirineto",
    "Fabiana Câmara", "Célio Lopes", "Vany Oliveira", "Marcos Barros",
    "André Nunes", "Diego Rocha", "Gustavo Melo", "Henrique Dias",
]
VEHICLE_TYPES = ["treminhao", "rodotrem", "pentatrem"]
USINA = (-19.9707, -47.7799)  # Delta/MG


def _rng(seed: str) -> random.Random:
    return random.Random(int(hashlib.md5(seed.encode()).hexdigest()[:12], 16))


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def generate_telemetry(tenant_id: str, n: int = 140) -> tuple[list[dict], list[dict]]:
    """Devolve (telemetria, alarmes) canônicos de `n` equipamentos."""
    now = datetime.now()
    tele, alarms = [], []
    for i in range(n):
        r = _rng(f"{tenant_id}:tele:{i}")
        tipo, modelos = EQUIP[i % len(EQUIP)]
        eq = str(200000 + i * 3 + (i % 7))
        engine_h = round(r.uniform(2500, 9800), 1)
        temp = round(_clamp(r.gauss(93, 7), 80, 110), 0)
        consumo = round(_clamp(r.gauss(35, 6), 26, 48), 1)
        n_alarms = int(_clamp(round(r.gauss(6, 5)), 0, 20))
        tele.append({
            "equipment_id": eq, "model": r.choice(modelos), "equipment_type": tipo,
            "frente": FRENTES[i % len(FRENTES)], "operator_name": r.choice(OPERADORES),
            "engine_hours": engine_h, "engine_temp": temp,
            "rpm": round(r.uniform(1500, 2200), 0), "fuel_consumption": consumo,
            "speed": round(r.uniform(0, 12), 1),
            "state": r.choice(["OPERANDO", "PARADA", "DESLOC P/ DESC", "MANOBRA"]),
            "ts": now - timedelta(minutes=r.randint(0, 240)),
        })
        for a in range(n_alarms):
            ar = _rng(f"{tenant_id}:al:{i}:{a}")
            alarms.append({
                "equipment_id": eq, "model": tele[-1]["model"],
                "ts": now - timedelta(hours=ar.randint(0, 72)),
                "alarm_type": ar.choice(["RPM MAXIMA MOTOR", "TEMPERATURA ALTA",
                                         "RPM MÁXIMO EM MANOBRA", "PRESSÃO ÓLEO BAIXA",
                                         "UTILIZAÇÃO DE PILOTO AUTOMÁTICO"]),
                "value": 1.0, "operation": tele[-1]["state"],
                "operator_name": tele[-1]["operator_name"], "online": "N",
            })
    return tele, alarms


def generate_route_history(tenant_id: str, n: int = 54) -> list[dict]:
    now = datetime.now()
    rows = []
    for i in range(n):
        r = _rng(f"{tenant_id}:rota:{i}")
        dist = round(r.uniform(45, 175), 1)
        fuel = round(dist * r.uniform(0.38, 0.52), 1)
        cost = round(dist * r.uniform(6.5, 9.5) + r.choice([0, 0, 14, 28, 42]), 2)
        rows.append({
            "vehicle_id": VEHICLE_TYPES[i % 3],
            "distance_km": dist, "total_cost": cost, "fuel_liters": fuel, "n_options": 4,
            "origin_lat": round(-19.6 - r.uniform(0, 0.6), 4),
            "origin_lon": round(-48.1 - r.uniform(0, 0.7), 4),
            "dest_lat": USINA[0], "dest_lon": USINA[1],
            "created_at": now - timedelta(days=r.randint(0, 24), hours=r.randint(0, 23),
                                          minutes=r.randint(0, 59)),
        })
    return rows


def seed_demo(tenant_id: str, ingest_store, route_log) -> dict:
    """Semeia a operação de demonstração (idempotente)."""
    seeded = {"telemetry": 0, "alarms": 0, "routes": 0}
    if ingest_store.telemetry_count(tenant_id) == 0:
        tele, alarms = generate_telemetry(tenant_id)
        seeded["telemetry"] = ingest_store.seed_canonical(tenant_id, tele, source="solinftec")
        seeded["alarms"] = ingest_store.seed_alarms_canonical(tenant_id, alarms, source="solinftec")
    if route_log.count(tenant_id) == 0:
        seeded["routes"] = route_log.seed_history(tenant_id, generate_route_history(tenant_id))
    return seeded
