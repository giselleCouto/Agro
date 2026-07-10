"""Enriquecimento de rotas: elevação, clima real, superfície, pedágios, restrições.

Todas as fontes são plugáveis e cobrem o Brasil inteiro:
  - Elevação : OpenTopoData (SRTM 30 m) — mesmo dataset do modelo SAJB v3
  - Clima    : Open-Meteo (chuva acumulada 7 dias + previsão) — sem API key
  - Superfície: tags OSM via GraphHopper `details=[surface]`, ou zonas do tenant
  - Pedágio  : matching geométrico das praças do tenant (base ANTT importável)
  - Restrição: avoid zones urbanas do tenant (raio; polígono no roadmap)
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx

from .geo import haversine_km, min_dist_to_polyline_km, resample
from .models import (
    AvoidZone,
    Segment,
    Surface,
    TollCrossing,
    TollPlaza,
)

OPENTOPO_URL = "https://api.opentopodata.org/v1/srtm30m"
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
ELEVATION_BATCH = 100
TOLL_MATCH_RADIUS_KM = 0.35


# ---------------------------------------------------------------------------
# Elevação (SRTM 30 m)
# ---------------------------------------------------------------------------

async def fetch_elevations(
    points: list[list[float]], client: httpx.AsyncClient
) -> list[Optional[float]]:
    """Elevação em metros por ponto; None quando a fonte falha (rota segue plana)."""
    results: list[Optional[float]] = []
    for i in range(0, len(points), ELEVATION_BATCH):
        chunk = points[i : i + ELEVATION_BATCH]
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in chunk)
        try:
            r = await client.get(OPENTOPO_URL, params={"locations": locs}, timeout=30)
            r.raise_for_status()
            data = r.json()
            results.extend(res.get("elevation") for res in data["results"])
        except (httpx.HTTPError, KeyError, ValueError):
            results.extend([None] * len(chunk))
        # rate limit da API pública (1 req/s); em produção, self-host do opentopodata
        if i + ELEVATION_BATCH < len(points):
            await asyncio.sleep(1.0)
    return results


# ---------------------------------------------------------------------------
# Clima real (Open-Meteo)
# ---------------------------------------------------------------------------

async def fetch_precip_7d_mm(
    lat: float, lon: float, client: httpx.AsyncClient
) -> Optional[float]:
    """Chuva acumulada nos últimos 7 dias no ponto médio da rota."""
    try:
        r = await client.get(
            OPENMETEO_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "precipitation_sum",
                "past_days": 7,
                "forecast_days": 1,
                "timezone": "America/Sao_Paulo",
            },
            timeout=15,
        )
        r.raise_for_status()
        sums = r.json()["daily"]["precipitation_sum"]
        return sum(v for v in sums[:-1] if v is not None)  # exclui a previsão de hoje
    except (httpx.HTTPError, KeyError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Segmentação da geometria em trechos com rampa/superfície
# ---------------------------------------------------------------------------

def build_segments(
    geometry: list[list[float]],
    elevations: Optional[list[Optional[float]]] = None,
    surface_lookup: Optional[dict[int, Surface]] = None,
    avoid_zones: Optional[list[AvoidZone]] = None,
    vehicle_id: str = "",
    slope_clip_pct: float = 20.0,
) -> list[Segment]:
    """Converte a polilinha reamostrada em segmentos com rampa e superfície.

    `surface_lookup` mapeia índice do ponto inicial -> superfície (vindo do
    GraphHopper details ou de zonas do tenant); ausente = UNKNOWN.
    """
    segments: list[Segment] = []
    zones = avoid_zones or []
    for i in range(1, len(geometry)):
        lat0, lon0 = geometry[i - 1]
        lat1, lon1 = geometry[i]
        dist = haversine_km(lat0, lon0, lat1, lon1)
        if dist <= 1e-6:
            continue
        slope = 0.0
        if elevations:
            e0, e1 = elevations[i - 1], elevations[i]
            if e0 is not None and e1 is not None:
                slope = (e1 - e0) / (dist * 1000.0) * 100.0
                slope = max(-slope_clip_pct, min(slope_clip_pct, slope))
        surface = (surface_lookup or {}).get(i - 1, Surface.UNKNOWN)
        urban = None
        for z in zones:
            if z.applies_to and vehicle_id not in z.applies_to:
                continue
            probes = ((lat0, lon0), ((lat0 + lat1) / 2, (lon0 + lon1) / 2), (lat1, lon1))
            if any(haversine_km(la, lo, z.lat, z.lon) <= z.radius_km for la, lo in probes):
                urban = z.name
                break
        segments.append(
            Segment(
                lat0=lat0, lon0=lon0, lat1=lat1, lon1=lon1,
                dist_km=dist, slope_pct=slope, surface=surface,
                in_urban_zone=urban,
            )
        )
    return segments


def ascent_descent_m(segments: list[Segment]) -> tuple[float, float]:
    up = sum(s.slope_pct / 100 * s.dist_km * 1000 for s in segments if s.slope_pct > 0)
    down = -sum(s.slope_pct / 100 * s.dist_km * 1000 for s in segments if s.slope_pct < 0)
    return round(up, 1), round(down, 1)


# ---------------------------------------------------------------------------
# Pedágios (por eixo) e restrições urbanas
# ---------------------------------------------------------------------------

def match_tolls(
    geometry: list[list[float]], plazas: list[TollPlaza]
) -> list[TollCrossing]:
    """Praças cujo ponto está a < 350 m do traçado real são consideradas cruzadas."""
    crossed = []
    for p in plazas:
        if min_dist_to_polyline_km(p.lat, p.lon, geometry) <= TOLL_MATCH_RADIUS_KM:
            crossed.append(
                TollCrossing(
                    name=p.name, lat=p.lat, lon=p.lon,
                    tariff_per_axle=p.tariff_per_axle,
                )
            )
    return crossed


def urban_violations(segments: list[Segment]) -> list[str]:
    seen: list[str] = []
    for s in segments:
        if s.in_urban_zone and s.in_urban_zone not in seen:
            seen.append(s.in_urban_zone)
    return seen


def surfaces_km(segments: list[Segment]) -> dict[str, float]:
    acc: dict[str, float] = {}
    for s in segments:
        acc[s.surface.value] = acc.get(s.surface.value, 0.0) + s.dist_km
    return {k: round(v, 2) for k, v in acc.items()}


__all__ = [
    "fetch_elevations",
    "fetch_precip_7d_mm",
    "build_segments",
    "ascent_descent_m",
    "match_tolls",
    "urban_violations",
    "surfaces_km",
    "resample",
]
