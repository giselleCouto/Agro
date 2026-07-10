"""Ingestão de telemetria — conecta a qualquer sistema de dados.

Recebe telemetria **bruta** (push/webhook) e de **provedores** (ex.: Solinftec
Flow API), normalizando tudo para um modelo canônico. A conexão a QUALQUER
sistema se dá por um *mapeamento* de campos (origem → canônico); provedores
conhecidos já vêm com o mapeamento pronto.

Fluxos suportados:
  - **push/webhook**  : POST /v1/ingest/telemetry (JSON) com um `mapping` ou `source`
  - **pull/HTTP**     : conector agenda/dispara GET numa API (Solinftec/genérica)
  - **arquivo**       : upload de CSV/XLSX (extrações), normalizado e ingerido

Baseado nos esquemas reais das extrações Solinftec (SOL_TELEMETRIA,
SGPA_ALARMES, HORAS_GERENCIAIS/SOL_GERENCIAIS, FLOW_HISTORICO).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Iterable

import httpx

from .db import AlarmRow, ConnectorRow, TelemetryRow, session_factory, write_lock

# Campos canônicos de telemetria (destino da normalização)
TELEMETRY_FIELDS = [
    "equipment_id", "model", "equipment_type", "operator_id", "operator_name",
    "ts", "unit", "frente", "state", "operation", "engine_hours", "odometer",
    "fuel_level", "fuel_consumption", "engine_temp", "rpm", "speed",
    "oil_pressure", "battery_voltage", "lat", "lon",
]
ALARM_FIELDS = ["equipment_id", "model", "ts", "alarm_type", "value",
                "operation", "operator_name", "online"]
_NUMERIC = {"engine_hours", "odometer", "fuel_level", "fuel_consumption",
            "engine_temp", "rpm", "speed", "oil_pressure", "battery_voltage",
            "lat", "lon", "value"}

# Mapeamentos prontos por provedor/dataset (origem -> canônico)
PROVIDER_MAPPINGS: dict[str, dict[str, dict[str, str]]] = {
    "solinftec": {
        # SOL_TELEMETRIA (telemetria bruta rica)
        "telemetry": {
            "CDEQUIPAMENTO": "equipment_id", "DSEQUIPAMENTO": "model",
            "CDOPERADOR": "operator_id", "DSOPERADOR": "operator_name",
            "DTHRLOCAL": "ts", "DSESTADO": "state",
            "VLHORIMETRO": "engine_hours", "VLHODOMETRO": "odometer",
            "VLNIVELCOMBUSTIVEL": "fuel_level", "VLTEMPERATURAOLEOMOTOR": "engine_temp",
            "VLRPMMOTOR": "rpm", "VLSENSORRADAR": "speed",
            "VLPRESSAOOLEO": "oil_pressure", "VLVOLTAGEMBATERIA": "battery_voltage",
        },
        # HORAS_GERENCIAIS / SOL_GERENCIAIS (horas por equipamento/operação)
        "gerenciais": {
            "COD_EQUIPAMENTO": "equipment_id", "DESC_EQUIPAMENTO": "model",
            "DESC_TIPO_EQUIPAMENTO": "equipment_type", "COD_OPERADOR": "operator_id",
            "NOME_OPERADOR": "operator_name", "DESC_UNIDADE": "unit",
            "DESC_GRUPO_EQUIPAMENTO": "frente", "DESC_OPERACAO": "operation",
            "DT_HR_LOCAL": "ts", "VL_HR_MOTOR_LIGADO": "engine_hours",
            "VL_VELOCIDADE_MEDIA": "speed", "VL_CONSUMO_COMBUSTIVEL": "fuel_consumption",
        },
        # SGPA_ALARMES
        "alarms": {
            "CDEQUIPAMENTO": "equipment_id", "DESCEQUIPAMENTO": "model",
            "DTHRLOCAL": "ts", "DESCTPALARME": "alarm_type", "VLALARME": "value",
            "DESCOPERACAO": "operation", "NOMEOPERADOR": "operator_name",
            "FGONLINE": "online",
        },
    },
}

_TS_FORMATS = ["%d/%m/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
               "%d/%m/%Y %H:%M", "%Y-%m-%d"]


def _parse_ts(v: Any) -> datetime | None:
    if v is None or v == "" or str(v).lower() == "none":
        return None
    if isinstance(v, datetime):
        return v
    s = str(v).strip().split(".")[0].replace("Z", "")
    for fmt in _TS_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _json_safe(rec: dict) -> dict:
    """Torna o registro serializável em JSON (datas/objetos viram string)."""
    out = {}
    for k, v in rec.items():
        out[str(k)] = v if (v is None or isinstance(v, (str, int, float, bool))) else str(v)
    return out


def _to_float(v: Any) -> float | None:
    if v is None or v == "" or str(v).lower() == "none":
        return None
    try:
        return float(str(v).replace(",", "."))
    except ValueError:
        return None


def resolve_mapping(source: str | None, dataset: str | None,
                    mapping: dict | None) -> dict[str, str]:
    """Mapa origem→canônico. Provedor conhecido tem mapa pronto; senão, usa o
    `mapping` fornecido; sem nada, assume que o registro já é canônico."""
    if mapping:
        return mapping
    if source and source.lower() in PROVIDER_MAPPINGS:
        ds = dataset or "telemetry"
        return PROVIDER_MAPPINGS[source.lower()].get(ds, {})
    return {}


def normalize(record: dict, mapping: dict[str, str], fields: list[str]) -> dict:
    """Normaliza um registro para o modelo canônico."""
    out: dict[str, Any] = {}
    if mapping:
        for src, canon in mapping.items():
            if src in record and canon in fields:
                out[canon] = record[src]
    else:
        # já canônico: copia os campos conhecidos
        for f in fields:
            if f in record:
                out[f] = record[f]
    # casts
    out["ts"] = _parse_ts(out.get("ts")) if "ts" in fields else None
    for f in _NUMERIC & set(out):
        out[f] = _to_float(out[f])
    for f in ("equipment_id", "operator_id"):
        if out.get(f) is not None:
            out[f] = str(out[f]).split(".")[0]  # "200085.0" -> "200085"
    return out


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class IngestStore:
    def __init__(self, engine=None):
        self._Session = session_factory(engine)

    def ingest_telemetry(self, tenant_id: str, records: Iterable[dict],
                         source: str, dataset: str | None,
                         mapping: dict | None = None) -> int:
        m = resolve_mapping(source, dataset, mapping)
        n = 0
        with write_lock(), self._Session() as s:
            for rec in records:
                c = normalize(rec, m, TELEMETRY_FIELDS)
                if not c.get("equipment_id"):
                    continue
                s.add(TelemetryRow(tenant_id=tenant_id, source=source, raw=_json_safe(rec),
                                   **{k: c.get(k) for k in TELEMETRY_FIELDS}))
                n += 1
            s.commit()
        return n

    def ingest_alarms(self, tenant_id: str, records: Iterable[dict],
                      source: str, mapping: dict | None = None) -> int:
        m = resolve_mapping(source, "alarms", mapping)
        n = 0
        with write_lock(), self._Session() as s:
            for rec in records:
                c = normalize(rec, m, ALARM_FIELDS)
                if not c.get("equipment_id"):
                    continue
                s.add(AlarmRow(tenant_id=tenant_id, source=source,
                               **{k: c.get(k) for k in ALARM_FIELDS}))
                n += 1
            s.commit()
        return n

    def telemetry_count(self, tenant_id: str) -> int:
        with self._Session() as s:
            return s.query(TelemetryRow).filter(TelemetryRow.tenant_id == tenant_id).count()

    def seed_canonical(self, tenant_id: str, records: Iterable[dict],
                       source: str = "solinftec") -> int:
        """Insere telemetria já canônica (para materialidade da demo)."""
        n = 0
        with write_lock(), self._Session() as s:
            for c in records:
                s.add(TelemetryRow(tenant_id=tenant_id, source=source, raw=_json_safe(c),
                                   **{k: c.get(k) for k in TELEMETRY_FIELDS}))
                n += 1
            s.commit()
        return n

    def seed_alarms_canonical(self, tenant_id: str, records: Iterable[dict],
                              source: str = "solinftec") -> int:
        n = 0
        with write_lock(), self._Session() as s:
            for c in records:
                s.add(AlarmRow(tenant_id=tenant_id, source=source,
                               **{k: c.get(k) for k in ALARM_FIELDS}))
                n += 1
            s.commit()
        return n

    def recent_telemetry(self, tenant_id: str, limit: int = 100) -> list[dict]:
        with self._Session() as s:
            rows = s.query(TelemetryRow).filter(TelemetryRow.tenant_id == tenant_id)\
                .order_by(TelemetryRow.id.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]

    def latest_per_equipment(self, tenant_id: str) -> list[dict]:
        """Último registro por equipamento (para montar a frota real)."""
        with self._Session() as s:
            rows = s.query(TelemetryRow).filter(TelemetryRow.tenant_id == tenant_id)\
                .order_by(TelemetryRow.id.desc()).limit(20000).all()
        seen, out = set(), []
        for r in rows:
            if r.equipment_id in seen:
                continue
            seen.add(r.equipment_id)
            out.append(r)
        return [r.to_dict() | {"raw": r.raw} for r in out]

    def alarm_counts(self, tenant_id: str) -> dict[str, int]:
        with self._Session() as s:
            rows = s.query(AlarmRow.equipment_id).filter(AlarmRow.tenant_id == tenant_id).all()
        counts: dict[str, int] = {}
        for (eq,) in rows:
            counts[eq] = counts.get(eq, 0) + 1
        return counts

    def stats(self, tenant_id: str) -> dict:
        with self._Session() as s:
            tel = s.query(TelemetryRow).filter(TelemetryRow.tenant_id == tenant_id)
            n_tel = tel.count()
            n_alarm = s.query(AlarmRow).filter(AlarmRow.tenant_id == tenant_id).count()
            sources = {}
            for (src,) in s.query(TelemetryRow.source).filter(
                    TelemetryRow.tenant_id == tenant_id).all():
                sources[src] = sources.get(src, 0) + 1
            n_equip = len({e for (e,) in s.query(TelemetryRow.equipment_id).filter(
                TelemetryRow.tenant_id == tenant_id).all()})
        return {"telemetry_records": n_tel, "alarm_records": n_alarm,
                "equipments": n_equip, "by_source": sources}

    # -- conectores --
    def register_connector(self, tenant_id: str, cfg: dict) -> dict:
        with write_lock(), self._Session() as s:
            row = ConnectorRow(
                tenant_id=tenant_id, name=cfg["name"], type=cfg["type"],
                base_url=cfg.get("base_url"), dataset=cfg.get("dataset"),
                auth=cfg.get("auth"), mapping=cfg.get("mapping"),
                schedule=cfg.get("schedule"), enabled=1 if cfg.get("enabled", True) else 0,
            )
            s.add(row); s.commit(); s.refresh(row)
            return row.to_dict()

    def list_connectors(self, tenant_id: str) -> list[dict]:
        with self._Session() as s:
            return [c.to_dict() for c in s.query(ConnectorRow)
                    .filter(ConnectorRow.tenant_id == tenant_id).all()]

    def get_connector(self, tenant_id: str, cid: int) -> ConnectorRow | None:
        with self._Session() as s:
            row = s.get(ConnectorRow, cid)
            return row if row and row.tenant_id == tenant_id else None

    def mark_sync(self, cid: int, status: str) -> None:
        from datetime import datetime as _dt
        with write_lock(), self._Session() as s:
            row = s.get(ConnectorRow, cid)
            if row:
                row.last_sync = _dt.utcnow()
                row.last_status = status
                s.commit()


# ---------------------------------------------------------------------------
# Conectores HTTP (pull) e parsers de arquivo
# ---------------------------------------------------------------------------

def _auth_kwargs(auth: dict | None) -> dict:
    """Constrói headers/params a partir da config de autenticação do conector."""
    if not auth:
        return {}
    t = auth.get("type")
    if t == "bearer":
        return {"headers": {"Authorization": f"Bearer {auth.get('token', '')}"}}
    if t == "header":
        return {"headers": {auth.get("name", "X-API-Key"): auth.get("value", "")}}
    if t == "query":
        return {"params": {auth.get("key", "apikey"): auth.get("value", "")}}
    if t == "basic":
        return {"auth": (auth.get("user", ""), auth.get("password", ""))}
    return {}


def _extract_records(payload: Any) -> list[dict]:
    """Aceita lista de objetos ou {data|results|records|rows: [...]}."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "records", "rows", "items"):
            if isinstance(payload.get(key), list):
                return [r for r in payload[key] if isinstance(r, dict)]
        return [payload]
    return []


async def sync_http_connector(store: IngestStore, tenant_id: str,
                              connector: ConnectorRow, client: httpx.AsyncClient) -> dict:
    """Puxa dados de uma API (Solinftec Flow ou HTTP genérica) e ingere."""
    kwargs = _auth_kwargs(connector.auth)
    r = await client.get(connector.base_url, timeout=45, **kwargs)
    r.raise_for_status()
    records = _extract_records(r.json())
    dataset = connector.dataset or "telemetry"
    source = "solinftec" if connector.type == "solinftec_flow" else (connector.name or "http")
    if dataset == "alarms":
        n = store.ingest_alarms(tenant_id, records, source, connector.mapping)
    else:
        n = store.ingest_telemetry(tenant_id, records, source, dataset, connector.mapping)
    store.mark_sync(connector.id, f"ok: {n} registros")
    return {"ingested": n, "records_received": len(records)}


def parse_tabular(content: bytes, filename: str) -> list[dict]:
    """Converte CSV/XLSX (extração) em lista de dicts."""
    name = filename.lower()
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        return list(csv.DictReader(io.StringIO(text)))
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        it = ws.iter_rows(values_only=True)
        header = [str(h) for h in next(it)]
        out = [dict(zip(header, row)) for row in it]
        wb.close()
        return out
    raise ValueError("formato não suportado (use CSV ou XLSX)")
