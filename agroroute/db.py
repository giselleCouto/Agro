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

def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


def make_engine(url: Optional[str] = None):
    url = url or database_url()
    kwargs: dict = {"future": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
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
    "make_engine",
    "get_engine",
    "session_factory",
    "database_url",
    "write_lock",
    "select",
]
