"""Multi-tenancy lastreado em banco de dados.

Cada usina/transportadora é um tenant isolado por API key, com sua própria
configuração (diesel, frota, pedágios, zonas restritas, roteirizador).

A fonte de verdade é o banco (ver [db.py](db.py)). Na primeira execução, o
arquivo semente `data/tenants.json` é carregado para a tabela `tenants`; depois
disso o banco manda. Produção: PostgreSQL com row-level security por tenant.
"""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from .db import TenantRow, session_factory, write_lock
from .models import TenantConfig

# prefixo dos tenants de demonstração efêmeros (um por visitante)
DEMO_SESSION_PREFIX = "demo-s-"


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
            try:
                s.commit()
            except IntegrityError:
                # outro worker semeou ao mesmo tempo (Postgres multi-worker)
                s.rollback()
                return 0
        return inserted

    def create_demo_session(self, base_tenant_id: str) -> TenantConfig | None:
        """Cria um tenant de demonstração ISOLADO, clonando a config do demo base.

        Cada visitante ganha seu próprio sandbox (chave e cota próprias), para que
        a demonstração nunca 'acabe' para novos usuários. `is_demo=1` mantém os
        mesmos limites (5 rotas, sem escrita) do demo compartilhado.
        """
        with write_lock(), self._Session() as s:
            base = s.get(TenantRow, base_tenant_id)
            if base is None:
                return None
            tid = f"{DEMO_SESSION_PREFIX}{int(time.time())}-{secrets.token_hex(3)}"
            row = TenantRow(
                tenant_id=tid, name=f"Demonstração — {base.name}",
                api_key=f"demo_{secrets.token_urlsafe(18)}",
                diesel_price=base.diesel_price, osrm_base_url=base.osrm_base_url,
                graphhopper_url=base.graphhopper_url, graphhopper_key=base.graphhopper_key,
                avoid_zones=base.avoid_zones, toll_plazas=base.toll_plazas,
                fleet=base.fleet, private_road_data=base.private_road_data, is_demo=1,
            )
            s.add(row)
            try:
                s.commit()
            except IntegrityError:
                s.rollback()
                return None
            return row.to_config()

    def expired_demo_sessions(self, ttl_seconds: int) -> list[str]:
        """IDs das sessões de demo efêmeras mais velhas que o TTL (para reciclar)."""
        cutoff = int(time.time()) - ttl_seconds
        out: list[str] = []
        with self._Session() as s:
            rows = s.query(TenantRow).filter(
                TenantRow.tenant_id.like(DEMO_SESSION_PREFIX + "%")
            ).all()
            for r in rows:
                try:
                    ts = int(r.tenant_id[len(DEMO_SESSION_PREFIX):].split("-")[0])
                except (ValueError, IndexError):
                    continue
                if ts < cutoff:
                    out.append(r.tenant_id)
        return out

    def delete_tenants(self, tenant_ids: list[str]) -> None:
        if not tenant_ids:
            return
        with write_lock(), self._Session() as s:
            s.query(TenantRow).filter(
                TenantRow.tenant_id.in_(tenant_ids)
            ).delete(synchronize_session=False)
            s.commit()

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
