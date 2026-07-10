"""Frota, manutenção preditiva e agregados para o dashboard.

Porta o modelo de desgaste do app NOKAHI Logística (Base44):
wear% = uso_atual / limite; severidade em faixas 50/75/90.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from .db import RouteLogRow, VehicleRow, session_factory, write_lock

COMPONENTS = [
    ("tires", "Pneus", "tire_km", "tire_limit_km", "km"),
    ("brakes", "Freios", "brake_km", "brake_limit_km", "km"),
    ("suspension", "Suspensão", "suspension_km", "suspension_limit_km", "km"),
    ("engine", "Motor", "engine_hours", "engine_limit_hours", "h"),
]


def predict_maintenance(v: dict) -> list[dict]:
    out = []
    for key, label, cur_f, lim_f, unit in COMPONENTS:
        cur = v.get(cur_f) or 0
        lim = v.get(lim_f) or 0
        wear = (cur / lim * 100) if lim > 0 else 0
        if wear >= 90:
            sev = "critical"
        elif wear >= 75:
            sev = "high"
        elif wear >= 50:
            sev = "medium"
        else:
            sev = "low"
        out.append({
            "component": key, "label": label, "unit": unit,
            "current": cur, "limit": lim,
            "wear_pct": round(min(wear, 100), 1),
            "remaining": round(lim - cur, 1), "severity": sev,
        })
    return out


class VehicleIn(BaseModel):
    plate: str = Field(min_length=1, max_length=20)
    type: str = "treminhao"
    display_name: str | None = Field(default=None, max_length=80)
    odometer_km: float = 0
    tire_km: float = 0
    brake_km: float = 0
    suspension_km: float = 0
    engine_hours: float = 0
    tire_limit_km: float = 80000
    brake_limit_km: float = 50000
    suspension_limit_km: float = 120000
    engine_limit_hours: float = 15000
    status: str = "active"


class VehicleStore:
    def __init__(self, engine=None):
        self._Session = session_factory(engine)

    def list(self, tenant_id: str) -> list[dict]:
        with self._Session() as s:
            rows = s.query(VehicleRow).filter(VehicleRow.tenant_id == tenant_id)\
                .order_by(VehicleRow.plate).all()
            return [r.to_dict() for r in rows]

    def list_with_maintenance(self, tenant_id: str) -> list[dict]:
        out = []
        for v in self.list(tenant_id):
            preds = predict_maintenance(v)
            worst = max(preds, key=lambda p: p["wear_pct"])
            out.append({**v, "maintenance": preds, "worst_severity": worst["severity"]})
        return out

    def create(self, tenant_id: str, v: VehicleIn) -> dict:
        with write_lock(), self._Session() as s:
            row = VehicleRow(tenant_id=tenant_id, **v.model_dump())
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.to_dict()

    def count(self, tenant_id: str) -> int:
        with self._Session() as s:
            return s.query(VehicleRow).filter(VehicleRow.tenant_id == tenant_id).count()

    def seed(self, tenant_id: str, vehicles: list[dict]) -> int:
        """Semeia veículos de exemplo só se o tenant ainda não tiver frota."""
        with write_lock(), self._Session() as s:
            exists = s.query(VehicleRow).filter(VehicleRow.tenant_id == tenant_id).first()
            if exists:
                return 0
            for v in vehicles:
                s.add(VehicleRow(tenant_id=tenant_id, **v))
            s.commit()
            return len(vehicles)


class RouteLogStore:
    def __init__(self, engine=None):
        self._Session = session_factory(engine)

    def log(self, tenant_id: str, job, best) -> None:
        if best is None or best.cost is None:
            return
        with write_lock(), self._Session() as s:
            s.add(RouteLogRow(
                tenant_id=tenant_id, vehicle_id=job.vehicle_id,
                distance_km=best.distance_km, total_cost=best.cost.total_cost,
                fuel_liters=best.cost.fuel_liters, n_options=1,
                origin_lat=job.origin_lat, origin_lon=job.origin_lon,
                dest_lat=job.dest_lat, dest_lon=job.dest_lon,
            ))
            s.commit()

    def recent(self, tenant_id: str, limit: int = 10) -> list[dict]:
        with self._Session() as s:
            rows = s.query(RouteLogRow).filter(RouteLogRow.tenant_id == tenant_id)\
                .order_by(RouteLogRow.created_at.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]

    def stats(self, tenant_id: str) -> dict:
        with self._Session() as s:
            rows = s.query(RouteLogRow).filter(RouteLogRow.tenant_id == tenant_id).all()
        n = len(rows)
        km = sum(r.distance_km or 0 for r in rows)
        cost = sum(r.total_cost or 0 for r in rows)
        fuel = sum(r.fuel_liters or 0 for r in rows)
        return {"routes": n, "total_km": round(km, 1),
                "total_cost": round(cost, 2), "total_fuel": round(fuel, 1)}


def fleet_summary(vehicles_with_maint: list[dict]) -> dict:
    by_status = {"active": 0, "maintenance": 0, "inactive": 0}
    sev_count = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    alerts = []
    for v in vehicles_with_maint:
        by_status[v.get("status", "active")] = by_status.get(v.get("status", "active"), 0) + 1
        for p in v["maintenance"]:
            if p["severity"] != "low":
                sev_count[p["severity"]] += 1
                alerts.append({
                    "plate": v["plate"], "type": v["type"],
                    "display_name": v.get("display_name"),
                    **p,
                })
    alerts.sort(key=lambda a: a["wear_pct"], reverse=True)
    needs = sum(1 for v in vehicles_with_maint if v["worst_severity"] in ("critical", "high"))
    return {
        "total": len(vehicles_with_maint),
        "by_status": by_status,
        "needs_maintenance": needs,
        "severity_counts": sev_count,
        "alerts": alerts,
    }


DEMO_VEHICLES = {
    "sajb": [
        {"plate": "SAJ-1A01", "type": "treminhao", "display_name": "Treminhão 01",
         "odometer_km": 240000, "tire_km": 73000, "brake_km": 31000,
         "suspension_km": 62000, "engine_hours": 8200, "status": "active"},
        {"plate": "SAJ-1B02", "type": "rodotrem", "display_name": "Rodotrem 02",
         "odometer_km": 310000, "tire_km": 41000, "brake_km": 43000,
         "suspension_km": 92000, "engine_hours": 12300, "status": "active"},
        {"plate": "SAJ-1C03", "type": "pentatrem", "display_name": "Pentatrem 03",
         "odometer_km": 95000, "tire_km": 20000, "brake_km": 15000,
         "suspension_km": 30000, "engine_hours": 5100, "status": "active"},
        {"plate": "SAJ-1D04", "type": "treminhao", "display_name": "Treminhão 04",
         "odometer_km": 400000, "tire_km": 78000, "brake_km": 49000,
         "suspension_km": 110000, "engine_hours": 14200, "status": "maintenance"},
    ],
    "demo-mg": [
        {"plate": "MG-2D01", "type": "treminhao", "display_name": "Treminhão MG-01",
         "odometer_km": 280000, "tire_km": 76500, "brake_km": 26000,
         "suspension_km": 101000, "engine_hours": 9000, "status": "active"},
        {"plate": "MG-2E02", "type": "rodotrem", "display_name": "Rodotrem MG-02",
         "odometer_km": 120000, "tire_km": 30000, "brake_km": 20000,
         "suspension_km": 40000, "engine_hours": 7000, "status": "active"},
        {"plate": "MG-2F03", "type": "treminhao", "display_name": "Treminhão MG-03",
         "odometer_km": 360000, "tire_km": 60000, "brake_km": 48500,
         "suspension_km": 55000, "engine_hours": 14100, "status": "active"},
    ],
}
