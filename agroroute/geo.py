"""Utilidades geométricas (haversine, reamostragem de polilinha)."""
from __future__ import annotations

import math

EARTH_R_KM = 6371.0088


def haversine_km(lat0: float, lon0: float, lat1: float, lon1: float) -> float:
    p0, p1 = math.radians(lat0), math.radians(lat1)
    dp = p1 - p0
    dl = math.radians(lon1 - lon0)
    a = math.sin(dp / 2) ** 2 + math.cos(p0) * math.cos(p1) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(math.sqrt(a))


def resample(geometry: list[list[float]], step_km: float = 0.25) -> list[list[float]]:
    """Reamostra a polilinha [[lat,lon],...] a cada ~step_km, preservando vértices-chave.

    Mantém granularidade suficiente para rampa (SRTM 30 m) sem explodir as
    chamadas de elevação em rotas longas.
    """
    if len(geometry) < 2:
        return geometry
    out = [geometry[0]]
    acc = 0.0
    for i in range(1, len(geometry)):
        lat0, lon0 = geometry[i - 1]
        lat1, lon1 = geometry[i]
        d = haversine_km(lat0, lon0, lat1, lon1)
        acc += d
        if acc >= step_km or i == len(geometry) - 1:
            out.append(geometry[i])
            acc = 0.0
    if out[-1] != geometry[-1]:
        out.append(geometry[-1])
    return out


def min_dist_to_polyline_km(
    lat: float, lon: float, geometry: list[list[float]]
) -> float:
    """Distância mínima aproximada de um ponto à polilinha (vértice mais próximo).

    A geometria OSRM overview=full tem vértices densos (~dezenas de metros),
    então a aproximação por vértice é adequada para matching de pedágio/zona.
    """
    return min(haversine_km(lat, lon, p[0], p[1]) for p in geometry)


def polyline_length_km(geometry: list[list[float]]) -> float:
    return sum(
        haversine_km(*geometry[i - 1], *geometry[i]) for i in range(1, len(geometry))
    )
