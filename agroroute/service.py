"""Orquestração: rota crua -> enriquecimento -> custo -> ranking.

Pipeline por job:
  1. provider (OSRM/GraphHopper) devolve N alternativas com geometria real
  2. reamostragem (~250 m) + elevação SRTM (se o provider não trouxe)
  3. clima real: chuva acumulada 7d no ponto médio (Open-Meteo) quando AUTO
  4. superfície: details do GraphHopper (tags OSM) ou UNKNOWN no OSRM público
  5. matching de pedágios do tenant + violações de zona urbana
  6. custo físico (combustível por rampa/peso/superfície/clima, pedágio por
     eixo com eixo suspenso no vazio, manutenção por desgaste)
  7. ranking por custo total, penalizando rotas inseguras

O lote roda com asyncio.gather + semáforo — várias rotas simultâneas.
"""
from __future__ import annotations

import asyncio

import httpx

from . import cost as cost_engine
from .enrich import (
    ascent_descent_m,
    build_segments,
    fetch_elevations,
    fetch_precip_7d_mm,
    match_tolls,
    surfaces_km,
    urban_violations,
)
from .geo import resample
from .models import (
    BatchRouteResponse,
    ClimateState,
    RouteJob,
    RouteJobResult,
    RouteOption,
    TenantConfig,
)
from .providers import OSRMProvider, RawRoute, provider_for_tenant

import math  # noqa: E402

from .geo import haversine_km  # noqa: E402

MAX_CONCURRENT_JOBS = 8
UNSAFE_PENALTY = 1e6  # rota que viola zona urbana nunca vence uma segura
TARGET_ROUTES = 4     # o sistema sempre tenta oferecer 4 rotas possíveis


async def _ensure_alternatives(provider, job, raw_routes, desired, client):
    """Completa até `desired` rotas gerando desvios por ponto intermediário.

    Quando o roteirizador devolve menos alternativas que o alvo, roteia por
    waypoints deslocados perpendicularmente à linha origem-destino (para os dois
    lados, em algumas distâncias), formando corredores reais e distintos.
    """
    if not raw_routes or len(raw_routes) >= desired:
        return raw_routes
    route_via = getattr(provider, "route_via", None)
    if not callable(route_via):
        return raw_routes
    o = (job.origin_lat, job.origin_lon)
    d = (job.dest_lat, job.dest_lon)
    dist = haversine_km(*o, *d)
    if dist < 1.0:
        return raw_routes
    midlat, midlon = (o[0] + d[0]) / 2, (o[1] + d[1]) / 2
    coslat = max(0.1, math.cos(math.radians(midlat)))
    vlat, vlon = d[0] - o[0], (d[1] - o[1]) * coslat
    norm = math.hypot(vlat, vlon) or 1.0
    plat, plon = -vlon / norm, vlat / norm  # unitário perpendicular (espaço escalado)
    dists = [r.distance_km for r in raw_routes]
    for frac in (0.10, 0.18, 0.28):
        for side in (1, -1):
            if len(raw_routes) >= desired:
                return raw_routes
            ddeg = (frac * dist) / 111.32
            wlat = midlat + plat * ddeg * side
            wlon = midlon + (plon / coslat) * ddeg * side
            extra = await route_via(o, (wlat, wlon), d, job.vehicle_id, client)
            if not extra or extra.distance_km <= 0:
                continue
            if extra.distance_km > 2.4 * dists[0]:          # desvio absurdo
                continue
            if any(abs(extra.distance_km - ed) / max(ed, 1) < 0.02 for ed in dists):
                continue                                     # muito parecida com outra
            raw_routes.append(extra)
            dists.append(extra.distance_km)
    return raw_routes


async def compute_job(
    job: RouteJob, tenant: TenantConfig, client: httpx.AsyncClient
) -> RouteJobResult:
    try:
        vehicle = tenant.vehicle(job.vehicle_id)
    except KeyError as e:
        return RouteJobResult(job_id=job.job_id, vehicle_id=job.vehicle_id,
                              options=[], error=str(e))
    provider = provider_for_tenant(tenant)
    args = (
        (job.origin_lat, job.origin_lon),
        (job.dest_lat, job.dest_lon),
        job.vehicle_id,
        job.max_alternatives,
        client,
    )
    try:
        raw_routes = await provider.routes(*args)
    except Exception as e:
        # GraphHopper do tenant fora do ar -> degrada para OSRM em vez de falhar
        if tenant.graphhopper_url:
            try:
                provider = OSRMProvider(tenant.osrm_base_url)
                raw_routes = await provider.routes(*args)
                for r in raw_routes:
                    r.provider = "osrm (fallback)"
            except Exception as e2:
                return RouteJobResult(job_id=job.job_id, vehicle_id=job.vehicle_id,
                                      options=[], error=f"roteirizador: {e} / fallback: {e2}")
        else:
            return RouteJobResult(job_id=job.job_id, vehicle_id=job.vehicle_id,
                                  options=[], error=f"roteirizador: {e}")

    # garante até 4 rotas possíveis (completa com desvios reais se faltar)
    desired = max(job.max_alternatives, TARGET_ROUTES)
    raw_routes = await _ensure_alternatives(provider, job, raw_routes, desired, client)
    for i, r in enumerate(raw_routes):
        r.name = "Principal" if i == 0 else f"Alternativa {i}"

    # clima real no ponto médio da rota principal (uma consulta por job)
    climate_k = None
    climate_state = job.climate
    if job.climate == ClimateState.AUTO and raw_routes:
        mid = raw_routes[0].geometry[len(raw_routes[0].geometry) // 2]
        precip = await fetch_precip_7d_mm(mid[0], mid[1], client)
        climate_k = cost_engine.resolve_climate_k(ClimateState.AUTO, precip)
        climate_state = cost_engine.classify_climate(precip)
    if climate_k is None:
        climate_k = cost_engine.resolve_climate_k(
            job.climate if job.climate != ClimateState.AUTO else ClimateState.SAFRA_MIX
        )
        if climate_state == ClimateState.AUTO:
            climate_state = ClimateState.SAFRA_MIX

    options = []
    for raw in raw_routes:
        options.append(
            await _enrich_and_cost(raw, job, tenant, vehicle, climate_state, climate_k, client)
        )

    def rank_key(o: RouteOption) -> float:
        base = o.cost.total_cost if o.cost else float("inf")
        return base + (0 if o.is_safe else UNSAFE_PENALTY)

    options.sort(key=rank_key)
    savings = 0.0
    priced = [o for o in options if o.cost]
    if len(priced) >= 2:
        savings = round(priced[-1].cost.total_cost - priced[0].cost.total_cost, 2)
    return RouteJobResult(
        job_id=job.job_id,
        vehicle_id=job.vehicle_id,
        options=options,
        best_option=options[0].name if options else None,
        savings_vs_worst=savings,
    )


async def _enrich_and_cost(
    raw: RawRoute,
    job: RouteJob,
    tenant: TenantConfig,
    vehicle,
    climate_state: ClimateState,
    climate_k: float,
    client: httpx.AsyncClient,
) -> RouteOption:
    if raw.elevations is not None:
        # GraphHopper: geometria já vem com elevação e superfície alinhadas
        points, elevations, surface_lookup = raw.geometry, raw.elevations, raw.surface_by_point
    else:
        points = resample(raw.geometry, step_km=0.25)
        elevations = await fetch_elevations(points, client)
        surface_lookup = {}

    # perfil de elevação para o gráfico do front (máx. ~120 pontos)
    elev_profile: list[list[float]] = []
    if elevations:
        from .geo import haversine_km

        km_acc = 0.0
        raw_profile = []
        for i, (pt, ele) in enumerate(zip(points, elevations)):
            if i > 0:
                km_acc += haversine_km(points[i - 1][0], points[i - 1][1], pt[0], pt[1])
            if ele is not None:
                raw_profile.append([round(km_acc, 3), round(float(ele), 1)])
        step = max(1, len(raw_profile) // 120)
        elev_profile = raw_profile[::step]

    segments = build_segments(
        points,
        elevations=elevations,
        surface_lookup=surface_lookup,
        avoid_zones=tenant.avoid_zones,
        vehicle_id=job.vehicle_id,
    )
    tolls = match_tolls(raw.geometry, tenant.toll_plazas)
    violations = urban_violations(segments)
    breakdown = cost_engine.compute_cost(
        segments=segments,
        tolls=tolls,
        vehicle=vehicle,
        occupancy=job.occupancy,
        climate=climate_state,
        climate_k=climate_k,
        diesel_price=tenant.diesel_price,
        round_trip=job.round_trip,
    )
    up, down = ascent_descent_m(segments)
    return RouteOption(
        name=raw.name,
        provider=raw.provider,
        distance_km=raw.distance_km,
        duration_min=raw.duration_min,
        geometry=raw.geometry,
        ascent_m=up,
        descent_m=down,
        elev_profile=elev_profile,
        surfaces_km=surfaces_km(segments),
        tolls=tolls,
        urban_violations=violations,
        is_safe=not violations,
        cost=breakdown,
    )


async def compute_batch(
    jobs: list[RouteJob], tenant: TenantConfig
) -> BatchRouteResponse:
    """Calcula vários pares OD simultaneamente (semáforo de concorrência)."""
    sem = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    async with httpx.AsyncClient() as client:

        async def bounded(job: RouteJob) -> RouteJobResult:
            async with sem:
                return await compute_job(job, tenant, client)

        results = await asyncio.gather(*(bounded(j) for j in jobs))
    return BatchRouteResponse(tenant_id=tenant.tenant_id, results=list(results))
