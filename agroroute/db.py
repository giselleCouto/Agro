"""Camada de banco de dados (SQLAlchemy).

Fonte de verdade do sistema: tenants, assinaturas e leads.

Padrão: SQLite local (`data/nokahi.db`) — zero infraestrutura, roda no Windows.
Produção: aponte `DATABASE_URL` para PostgreSQL (ex.:
`postgresql+psycopg://user:pass@host/nokahi`) — o mesmo schema serve, e é onde
entram RLS por tenant e backups. Ver README/roadmap.

As três tabelas são fracamente acopladas por `tenant_id` (string), sem FK
rígida, para que cada store possa ser testado isoladamente.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "nokahi.db"

# lock de escrita para o SQLite (evita "database is locked" sob concorrência)
_write_lock = threading.Lock()


def write_lock() -> threading.Lock:
    return _write_lock


class TenantRow(Base):
    __tablename__ = "tenants"
    tenant_id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    api_key = Column(String, nullable=False, unique=True, index=True)
    diesel_price = Column(Float, default=6.0)
    osrm_base_url = Column(String, default="https://router.project-osrm.org")
    graphhopper_url = Column(String, nullable=True)
    graphhopper_key = Column(String, nullable=True)
    avoid_zones = Column(JSON, default=list)
    toll_plazas = Column(JSON, default=list)
    fleet = Column(JSON, default=dict)
    private_road_data = Column(String, nullable=True)
    is_demo = Column(Integer, default=0)

    def to_config(self):
        from .models import TenantConfig

        return TenantConfig(
            tenant_id=self.tenant_id,
            name=self.name,
            api_key=self.api_key,
            diesel_price=self.diesel_price or 6.0,
            osrm_base_url=self.osrm_base_url or "https://router.project-osrm.org",
            graphhopper_url=self.graphhopper_url,
            graphhopper_key=self.graphhopper_key,
            avoid_zones=self.avoid_zones or [],
            toll_plazas=self.toll_plazas or [],
            fleet=self.fleet or {},
            private_road_data=self.private_road_data,
        )


class SubscriptionRow(Base):
    __tablename__ = "subscriptions"
    tenant_id = Column(String, primary_key=True)
    plan_id = Column(String, default="essencial")
    status = Column(String, default="trialing")
    period_end = Column(Float, default=0.0)
    routes_used_month = Column(Integer, default=0)
    usage_month = Column(String, default="")
    provider = Column(String, default="sandbox")
    provider_sub_id = Column(String, nullable=True)
    stripe_customer_id = Column(String, nullable=True)


class VehicleRow(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    plate = Column(String, nullable=False)
    type = Column(String, default="treminhao")   # treminhao | rodotrem | pentatrem
    display_name = Column(String, nullable=True)
    status = Column(String, default="active")     # active | maintenance | inactive
    odometer_km = Column(Float, default=0)
    tire_km = Column(Float, default=0)
    brake_km = Column(Float, default=0)
    suspension_km = Column(Float, default=0)
    engine_hours = Column(Float, default=0)
    tire_limit_km = Column(Float, default=80000)
    brake_limit_km = Column(Float, default=50000)
    suspension_limit_km = Column(Float, default=120000)
    engine_limit_hours = Column(Float, default=15000)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "tenant_id": self.tenant_id, "plate": self.plate,
            "type": self.type, "display_name": self.display_name, "status": self.status,
            "odometer_km": self.odometer_km, "tire_km": self.tire_km,
            "brake_km": self.brake_km, "suspension_km": self.suspension_km,
            "engine_hours": self.engine_hours, "tire_limit_km": self.tire_limit_km,
            "brake_limit_km": self.brake_limit_km,
            "suspension_limit_km": self.suspension_limit_km,
            "engine_limit_hours": self.engine_limit_hours,
        }


class WebhookEventRow(Base):
    """Dedup idempotente de eventos do Stripe (entrega at-least-once, fora de ordem)."""
    __tablename__ = "webhook_events"
    event_id = Column(String, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())


class RouteLogRow(Base):
    """Histórico de rotas calculadas (para o dashboard)."""
    __tablename__ = "route_logs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    vehicle_id = Column(String, nullable=True)
    distance_km = Column(Float, default=0)
    total_cost = Column(Float, default=0)
    fuel_liters = Column(Float, default=0)
    n_options = Column(Integer, default=0)
    origin_lat = Column(Float, default=0)
    origin_lon = Column(Float, default=0)
    dest_lat = Column(Float, default=0)
    dest_lon = Column(Float, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "created_at": self.created_at.isoformat() if self.created_at else None,
            "vehicle_id": self.vehicle_id, "distance_km": self.distance_km,
            "total_cost": self.total_cost, "fuel_liters": self.fuel_liters,
            "n_options": self.n_options,
        }


class TelemetryRow(Base):
    """Telemetria canônica ingerida (bruta ou normalizada de provedores)."""
    __tablename__ = "telemetry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    source = Column(String, index=True)          # solinftec | raw | <provedor>
    equipment_id = Column(String, index=True)
    model = Column(String, nullable=True)
    equipment_type = Column(String, nullable=True)
    operator_id = Column(String, nullable=True)
    operator_name = Column(String, nullable=True)
    ts = Column(DateTime, index=True, nullable=True)   # timestamp do dado
    unit = Column(String, nullable=True)
    frente = Column(String, nullable=True)
    state = Column(String, nullable=True)
    operation = Column(String, nullable=True)
    engine_hours = Column(Float, nullable=True)
    odometer = Column(Float, nullable=True)
    fuel_level = Column(Float, nullable=True)
    fuel_consumption = Column(Float, nullable=True)
    engine_temp = Column(Float, nullable=True)
    rpm = Column(Float, nullable=True)
    speed = Column(Float, nullable=True)
    oil_pressure = Column(Float, nullable=True)
    battery_voltage = Column(Float, nullable=True)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    ingested_at = Column(DateTime, server_default=func.now())
    raw = Column(JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "source": self.source, "equipment_id": self.equipment_id,
            "model": self.model, "equipment_type": self.equipment_type,
            "operator_name": self.operator_name, "ts": self.ts.isoformat() if self.ts else None,
            "unit": self.unit, "frente": self.frente, "state": self.state,
            "operation": self.operation, "engine_hours": self.engine_hours,
            "fuel_level": self.fuel_level, "fuel_consumption": self.fuel_consumption,
            "engine_temp": self.engine_temp, "rpm": self.rpm, "speed": self.speed,
            "oil_pressure": self.oil_pressure,
        }


class AlarmRow(Base):
    """Alarmes de telemetria (ex.: SGPA_ALARMES da Solinftec)."""
    __tablename__ = "alarms"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    source = Column(String, index=True)
    equipment_id = Column(String, index=True)
    model = Column(String, nullable=True)
    ts = Column(DateTime, index=True, nullable=True)
    alarm_type = Column(String, nullable=True)
    value = Column(Float, nullable=True)
    operation = Column(String, nullable=True)
    operator_name = Column(String, nullable=True)
    online = Column(String, nullable=True)
    ingested_at = Column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "equipment_id": self.equipment_id,
                "model": self.model, "ts": self.ts.isoformat() if self.ts else None,
                "alarm_type": self.alarm_type, "value": self.value,
                "operation": self.operation, "operator_name": self.operator_name}


class ConnectorRow(Base):
    """Conector de dados por tenant (Solinftec Flow, HTTP genérico, webhook, arquivo)."""
    __tablename__ = "connectors"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)        # solinftec_flow | generic_http | webhook | file
    base_url = Column(String, nullable=True)
    dataset = Column(String, nullable=True)      # telemetry | alarms | gerenciais | historico
    auth = Column(JSON, nullable=True)           # {header/query/token} — segredos
    mapping = Column(JSON, nullable=True)        # campo_origem -> campo_canônico
    schedule = Column(String, nullable=True)     # ex.: "5m", "1h", "1d"
    enabled = Column(Integer, default=1)
    last_sync = Column(DateTime, nullable=True)
    last_status = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    def to_dict(self, include_secrets: bool = False) -> dict:
        d = {
            "id": self.id, "name": self.name, "type": self.type, "base_url": self.base_url,
            "dataset": self.dataset, "mapping": self.mapping, "schedule": self.schedule,
            "enabled": bool(self.enabled),
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "last_status": self.last_status,
        }
        if include_secrets:
            d["auth"] = self.auth
        return d


class LeadRow(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, server_default=func.now())
    name = Column(String, nullable=False)
    company = Column(String, nullable=True)
    email = Column(String, nullable=False, index=True)
    phone = Column(String, nullable=True)
    role = Column(String, nullable=True)
    fleet_size = Column(String, nullable=True)
    message = Column(Text, nullable=True)
    source = Column(String, default="landing")
    ip = Column(String, nullable=True)
    status = Column(String, default="novo")  # novo | contatado | qualificado | descartado

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "name": self.name,
            "company": self.company,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "fleet_size": self.fleet_size,
            "message": self.message,
            "source": self.source,
            "status": self.status,
        }


# ---------------------------------------------------------------------------
# Engine / sessão
# ---------------------------------------------------------------------------

def normalize_db_url(url: str) -> str:
    """Ajusta a URL para o SQLAlchemy. Railway/Heroku entregam `postgres://`,
    que o SQLAlchemy não aceita — vira `postgresql://` (dialeto psycopg2)."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return normalize_db_url(url.strip())
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


def make_engine(url: Optional[str] = None):
    url = normalize_db_url((url or database_url()).strip())
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Postgres em produção: conexões resilientes a quedas do pool (Railway)
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = 300
    return create_engine(url, **kwargs)


_engine = None
_Session = None


def get_engine():
    global _engine, _Session
    if _engine is None:
        _engine = make_engine()
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def session_factory(engine=None):
    """Devolve um sessionmaker ligado ao engine dado (ou ao engine global)."""
    if engine is not None:
        Base.metadata.create_all(engine)
        return sessionmaker(bind=engine, expire_on_commit=False, future=True)
    get_engine()
    return _Session


__all__ = [
    "Base",
    "TenantRow",
    "SubscriptionRow",
    "LeadRow",
    "VehicleRow",
    "WebhookEventRow",
    "RouteLogRow",
    "TelemetryRow",
    "AlarmRow",
    "ConnectorRow",
    "make_engine",
    "get_engine",
    "session_factory",
    "database_url",
    "write_lock",
    "select",
]
