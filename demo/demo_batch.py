"""Demo ao vivo: calcula 2 jobs em lote contra OSRM + Open-Meteo + SRTM reais.

Uso:  python demo/demo_batch.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agroroute.models import ClimateState, RouteJob
from agroroute.service import compute_batch
from agroroute.tenancy import TenantStore

USINA = (-21.3436637, -48.3050909)  # COA


async def main():
    store = TenantStore(Path(__file__).resolve().parent.parent / "data" / "tenants.json")
    tenant = store.by_api_key("sajb-dev-key-troque-em-producao")
    jobs = [
        RouteJob(
            job_id="talhao-norte", vehicle_id="rodotrem",
            origin_lat=-21.05, origin_lon=-48.15,
            dest_lat=USINA[0], dest_lon=USINA[1],
            climate=ClimateState.AUTO, max_alternatives=3,
        ),
        RouteJob(
            job_id="talhao-leste", vehicle_id="treminhao",
            origin_lat=-21.30, origin_lon=-48.05,
            dest_lat=USINA[0], dest_lon=USINA[1],
            climate=ClimateState.AUTO, max_alternatives=3,
        ),
    ]
    resp = await compute_batch(jobs, tenant)
    for res in resp.results:
        print(f"\n=== {res.job_id} ({res.vehicle_id}) ===")
        if res.error:
            print("ERRO:", res.error)
            continue
        for o in res.options:
            c = o.cost
            print(
                f"  {o.name:15s} {o.distance_km:6.1f} km | subida {o.ascent_m:6.0f} m"
                f" | {c.fuel_liters:6.1f} L | pedágio R$ {c.toll_cost:6.2f}"
                f" | manut R$ {c.maintenance_cost:7.2f} | TOTAL R$ {c.total_cost:8.2f}"
                f" | clima={c.climate_state.value} (k={c.climate_k_applied})"
                f" | {'SEGURA' if o.is_safe else 'VIOLA: ' + ','.join(o.urban_violations)}"
            )
        print(f"  Melhor: {res.best_option} | economia vs pior: R$ {res.savings_vs_worst}")


if __name__ == "__main__":
    asyncio.run(main())
