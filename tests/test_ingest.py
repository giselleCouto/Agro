"""Testes da ingestão de telemetria (Solinftec + genérico + conectores)."""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from agroroute import ingest as ing
from agroroute.api import app

client = TestClient(app)
KEY = {"X-API-Key": "demo-key"}   # tenant "demo" — isolado da demo-mg

SOL_TELEMETRIA = [
    {"CDEQUIPAMENTO": "200085", "DSEQUIPAMENTO": "JOHN DEERE CH570", "CDOPERADOR": "60006590",
     "DSOPERADOR": "FABRICIO SOUZA", "DTHRLOCAL": "01/11/2025 05:40:04", "DSESTADO": "PARADA",
     "VLHORIMETRO": "7838.3", "VLNIVELCOMBUSTIVEL": "50.75", "VLTEMPERATURAOLEOMOTOR": "95",
     "VLRPMMOTOR": "1800", "VLPRESSAOOLEO": "4.2"},
    {"CDEQUIPAMENTO": "210407", "DSEQUIPAMENTO": "MASSEY FERGUSON MF 772", "CDOPERADOR": "60019532",
     "DSOPERADOR": "EVERTON MACIEL", "DTHRLOCAL": "01/11/2025 05:41:00", "DSESTADO": "OPERANDO",
     "VLHORIMETRO": "5120.0", "VLTEMPERATURAOLEOMOTOR": "104", "VLRPMMOTOR": "2100"},
]
SGPA_ALARMES = [
    {"CDEQUIPAMENTO": "200085", "DESCEQUIPAMENTO": "JOHN DEERE CH570",
     "DTHRLOCAL": "02/11/2025 12:23:53", "DESCTPALARME": "RPM MAXIMA MOTOR", "VLALARME": "1",
     "DESCOPERACAO": "CORTAR CANA - MEC", "NOMEOPERADOR": "FABRICIO SOUZA", "FGONLINE": "N"},
    {"CDEQUIPAMENTO": "200085", "DESCEQUIPAMENTO": "JOHN DEERE CH570",
     "DTHRLOCAL": "02/11/2025 12:24:10", "DESCTPALARME": "TEMPERATURA ALTA", "VLALARME": "1",
     "DESCOPERACAO": "MANOBRA", "NOMEOPERADOR": "FABRICIO SOUZA", "FGONLINE": "N"},
]


def test_normalize_solinftec_telemetry():
    m = ing.resolve_mapping("solinftec", "telemetry", None)
    c = ing.normalize(SOL_TELEMETRIA[0], m, ing.TELEMETRY_FIELDS)
    assert c["equipment_id"] == "200085"          # sem ".0"
    assert c["model"] == "JOHN DEERE CH570"
    assert c["engine_hours"] == 7838.3            # cast numérico
    assert c["engine_temp"] == 95.0
    assert c["ts"] is not None                    # data parseada
    assert c["state"] == "PARADA"


def test_resolve_mapping_generic_and_known():
    assert ing.resolve_mapping("solinftec", "alarms", None)["DESCTPALARME"] == "alarm_type"
    custom = {"vehicle": "equipment_id", "temp": "engine_temp"}
    assert ing.resolve_mapping("qualquer", None, custom) == custom


def test_parse_tabular_csv():
    csv_bytes = b"CDEQUIPAMENTO,DSEQUIPAMENTO,VLHORIMETRO\n200085,CH570,7838.3\n"
    recs = ing.parse_tabular(csv_bytes, "x.csv")
    assert recs[0]["CDEQUIPAMENTO"] == "200085"


def test_ingest_telemetry_endpoint_and_stats():
    r = client.post("/v1/ingest/telemetry",
                    json={"source": "solinftec", "dataset": "telemetry", "records": SOL_TELEMETRIA},
                    headers=KEY)
    assert r.status_code == 200 and r.json()["ingested"] == 2
    client.post("/v1/ingest/alarms",
                json={"source": "solinftec", "records": SGPA_ALARMES}, headers=KEY)
    st = client.get("/v1/ingest/stats", headers=KEY).json()
    assert st["telemetry_records"] >= 2
    assert st["alarm_records"] >= 2
    assert st["equipments"] >= 2
    assert "solinftec" in st["by_source"]


def test_overview_uses_ingested_data():
    client.post("/v1/ingest/telemetry",
                json={"source": "solinftec", "records": SOL_TELEMETRIA}, headers=KEY)
    d = client.get("/v1/intel/overview", headers=KEY).json()
    assert "ingerida" in d["fonte"]               # usou telemetria real
    assert d["kpis_manutencao"]["totalVeiculos"] >= 2


def test_ingest_rejects_empty():
    assert client.post("/v1/ingest/telemetry", json={"records": []}, headers=KEY).status_code == 422


def test_connector_register_and_list():
    r = client.post("/v1/connectors", json={
        "name": "Solinftec Flow", "type": "solinftec_flow",
        "base_url": "https://flow-api.saas-solinftec.com/telemetria",
        "dataset": "telemetry", "auth": {"type": "bearer", "token": "segredo"},
        "schedule": "5m"}, headers=KEY)
    assert r.status_code == 200
    lst = client.get("/v1/connectors", headers=KEY).json()["connectors"]
    assert any(c["type"] == "solinftec_flow" for c in lst)
    # segredo não vaza na listagem
    assert all("auth" not in c for c in lst)


def test_providers_endpoint():
    p = client.get("/v1/ingest/providers").json()
    assert "solinftec" in p
    assert "telemetry" in p["solinftec"] and "alarms" in p["solinftec"]
