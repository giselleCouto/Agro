"""Multi-tenancy lastreado em banco de dados.

Cada usina/transportadora é um tenant isolado por API key, com sua própria
configuração (diesel, frota, pedágios, zonas restritas, roteirizador).

A fonte de verdade é o banco (ver [db.py](db.py)). Na primeira execução, o
arquivo semente `data/tenants.json` é carregado para a tabela `tenants`; depois
disso o banco manda. Produção: PostgreSQL com row-level security por tenant.
"""
from __future__ import annotations

import json
from pathlib import Path

from .db import TenantRow, session_factory, write_lock
from .models import TenantConfig


class TenantStore:
    def __init__(self, seed_path: str | Path | None = None, engine=None):
        self._Session = session_factory(engine)
        if seed_path:
            self.seed_from_json(Path(seed_path))

    def seed_from_json(self, path: Path) -> int:
        """Carrega tenants do JSON para o banco (idempotente por tenant_id)."""
        if not path.exists():
            return 0
        raw = json.loads(path.read_text(encoding="utf-8"))
        inserted = 0
        with write_lock(), self._Session() as s:
            for t in raw.get("tenants", []):
                exists = s.get(TenantRow, t["tenant_id"])
                if exists:
                    continue
                s.add(TenantRow(
                    tenant_id=t["tenant_id"],
                    name=t["name"],
                    api_key=t["api_key"],
                    diesel_price=t.get("diesel_price", 6.0),
                    osrm_base_url=t.get("osrm_base_url", "https://router.project-osrm.org"),
                    graphhopper_url=t.get("graphhopper_url"),
                    graphhopper_key=t.get("graphhopper_key"),
                    avoid_zones=t.get("avoid_zones", []),
                    toll_plazas=t.get("toll_plazas", []),
                    fleet=t.get("fleet", {}),
                    private_road_data=t.get("private_road_data"),
                    is_demo=1 if t.get("is_demo") else 0,
                ))
                inserted += 1
            s.commit()
        return inserted

    def by_api_key(self, api_key: str) -> TenantConfig | None:
        with self._Session() as s:
            row = s.query(TenantRow).filter(TenantRow.api_key == api_key).first()
            return row.to_config() if row else None

    def by_id(self, tenant_id: str) -> TenantConfig | None:
        with self._Session() as s:
            row = s.get(TenantRow, tenant_id)
            return row.to_config() if row else None

    def is_demo(self, tenant_id: str) -> bool:
        with self._Session() as s:
            row = s.get(TenantRow, tenant_id)
            return bool(row and row.is_demo)

    def all(self) -> list[TenantConfig]:
        with self._Session() as s:
            return [r.to_config() for r in s.query(TenantRow).all()]
