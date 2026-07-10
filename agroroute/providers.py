"""Roteirizadores plugáveis: OSRM (default) e GraphHopper (recomendado p/ produção).

OSRM público usa perfil de carro — serve para geometria/alternativas, mas não
sabe restrições de caminhão. Para produção NOKAHI:
  * self-host OSRM com perfil truck customizado, OU
  * self-host GraphHopper com custom models por veículo (peso, dimensões,
    superfície, priority areas p/ zonas urbanas) + dados OSM Brasil, onde as
    estradas particulares das usinas entram como OSM extract privado
    (`access=private` mantido no import).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from .models import Surface

# Mapeamento das tags OSM `surface` -> categorias do modelo de custo
OSM_SURFACE_MAP: dict[str, Surface] = {
    "asphalt": Surface.ASPHALT,
    "paved": Surface.ASPHALT,
    "concrete": Surface.CONCRETE,
    "paving_stones": Surface.CONCRETE,
    "gravel": Surface.GRAVEL,
    "fine_gravel": Surface.GRAVEL,
    "compacted": Surface.GRAVEL,
    "unpaved": Surface.DIRT,
    "ground": Surface.DIRT,
    "dirt": Surface.DIRT,
    "earth": Surface.DIRT,
    "mud": Surface.DIRT,
    "sand": Surface.SAND,
}


class RawRoute:
    """Rota crua do provider antes do enriquecimento."""

    def __init__(
        self,
        name: str,
        provider: str,
        geometry: list[list[float]],  # [[lat, lon], ...]
        distance_km: float,
        duration_min: float,
        surface_by_point: dict[int, Surface] | None = None,
        elevations: list[float | None] | None = None,
    ):
        self.name = name
        self.provider = provider
        self.geometry = geometry
        self.distance_km = distance_km
        self.duration_min = duration_min
        self.surface_by_point = surface_by_point or {}
        # elevações já embutidas na resposta (GraphHopper elevation=true);
        # quando None, o service busca no SRTM via OpenTopoData
        self.elevations = elevations


class RoutingProvider(ABC):
    @abstractmethod
    async def routes(
        self,
        origin: tuple[float, float],
        dest: tuple[float, float],
        vehicle_id: str,
        max_alternatives: int,
        client: httpx.AsyncClient,
    ) -> list[RawRoute]:
        ...

    async def route_via(
        self,
        origin: tuple[float, float],
        waypoint: tuple[float, float],
        dest: tuple[float, float],
        vehicle_id: str,
        client: httpx.AsyncClient,
    ) -> RawRoute | None:
        """Rota única passando por um ponto intermediário (gera alternativas).

        Usado para completar até N rotas quando o roteirizador devolve poucas.
        Padrão: sem suporte (None); implementado por OSRM e GraphHopper.
        """
        return None


class OSRMProvider(RoutingProvider):
    """OSRM com geometria real completa (overview=full, geometries=geojson)."""

    def __init__(self, base_url: str = "https://router.project-osrm.org"):
        self.base_url = base_url.rstrip("/")

    async def routes(self, origin, dest, vehicle_id, max_alternatives, client):
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{origin[1]:.6f},{origin[0]:.6f};{dest[1]:.6f},{dest[0]:.6f}"
        )
        r = await client.get(
            url,
            params={
                # OSRM público limita a 3 alternativas; o restante até o alvo
                # (4 rotas) é completado por desvios em _ensure_alternatives
                "alternatives": str(min(max_alternatives, 3)),
                "overview": "full",
                "geometries": "geojson",
                "steps": "false",
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM: {data.get('code')} {data.get('message', '')}")
        out = []
        for i, route in enumerate(data["routes"]):
            coords = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
            out.append(
                RawRoute(
                    name="Principal" if i == 0 else f"Alternativa {i}",
                    provider="osrm",
                    geometry=coords,
                    distance_km=round(route["distance"] / 1000, 2),
                    duration_min=round(route["duration"] / 60, 1),
                )
            )
        return out

    async def route_via(self, origin, waypoint, dest, vehicle_id, client):
        url = (
            f"{self.base_url}/route/v1/driving/"
            f"{origin[1]:.6f},{origin[0]:.6f};"
            f"{waypoint[1]:.6f},{waypoint[0]:.6f};"
            f"{dest[1]:.6f},{dest[0]:.6f}"
        )
        try:
            r = await client.get(
                url,
                params={"overview": "full", "geometries": "geojson",
                        "steps": "false", "alternatives": "false"},
                timeout=30,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None
            route = data["routes"][0]
            coords = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
            return RawRoute(
                name="Alternativa", provider="osrm", geometry=coords,
                distance_km=round(route["distance"] / 1000, 2),
                duration_min=round(route["duration"] / 60, 1),
            )
        except (httpx.HTTPError, KeyError, ValueError):
            return None


def _circle_polygon(lat: float, lon: float, radius_km: float, n: int = 20) -> list:
    """Aproxima um círculo por polígono GeoJSON [[lon, lat], ...] fechado."""
    import math

    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
    ring = [
        [lon + dlon * math.cos(2 * math.pi * i / n),
         lat + dlat * math.sin(2 * math.pi * i / n)]
        for i in range(n)
    ]
    ring.append(ring[0])
    return [ring]


class GraphHopperProvider(RoutingProvider):
    """GraphHopper self-hosted/cloud: perfil truck, elevação e superfície nativos.

    Em modo flexível (sem CH), envia custom_model por requisição:
      - `max_weight < PBT do CVC` bloqueia vias com limite legal insuficiente
      - zonas urbanas do tenant viram `areas` com prioridade ~0 -> as
        alternativas retornadas JÁ desviam das cidades, em vez de só
        sinalizar violação a posteriori.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        profile: str = "truck",
        tenant=None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.profile = profile
        self.tenant = tenant

    def _request_custom_model(self, vehicle_id: str) -> dict | None:
        if self.tenant is None:
            return None
        priority = []
        try:
            vehicle = self.tenant.vehicle(vehicle_id)
            priority.append(
                {"if": f"max_weight < {vehicle.pbt_t:.0f}", "multiply_by": "0"}
            )
        except KeyError:
            pass
        features = []
        for i, z in enumerate(self.tenant.avoid_zones):
            if z.applies_to and vehicle_id not in z.applies_to:
                continue
            features.append(
                {
                    "type": "Feature",
                    "id": f"zone_{i}",
                    "properties": {"name": z.name},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": _circle_polygon(z.lat, z.lon, z.radius_km),
                    },
                }
            )
            # 0.02 desvia fortemente mas mantém roteável se origem/destino
            # estiverem dentro da própria zona
            priority.append({"if": f"in_zone_{i}", "multiply_by": "0.02"})
        if not priority:
            return None
        model: dict = {"priority": priority}
        if features:
            model["areas"] = {"type": "FeatureCollection", "features": features}
        return model

    async def routes(self, origin, dest, vehicle_id, max_alternatives, client):
        body = {
            "points": [[origin[1], origin[0]], [dest[1], dest[0]]],
            "profile": self.profile,
            "elevation": True,
            "points_encoded": False,
            "details": ["surface", "toll", "road_class"],
            "algorithm": "alternative_route",
            "alternative_route.max_paths": max_alternatives,
            "alternative_route.max_weight_factor": 1.6,
            "alternative_route.max_share_factor": 0.8,
            "instructions": False,
        }
        custom_model = self._request_custom_model(vehicle_id)
        if custom_model:
            body["custom_model"] = custom_model
            body["ch.disable"] = True
        params = {"key": self.api_key} if self.api_key else {}
        r = await client.post(
            f"{self.base_url}/route", json=body, params=params, timeout=45
        )
        r.raise_for_status()
        data = r.json()
        out = []
        for i, path in enumerate(data.get("paths", [])):
            raw_coords = path["points"]["coordinates"]
            coords = [[c[1], c[0]] for c in raw_coords]
            elevations = (
                [c[2] for c in raw_coords] if raw_coords and len(raw_coords[0]) >= 3 else None
            )
            surface_by_point: dict[int, Surface] = {}
            for start, end, value in path.get("details", {}).get("surface", []):
                surf = OSM_SURFACE_MAP.get(str(value), Surface.UNKNOWN)
                for idx in range(start, end):
                    surface_by_point[idx] = surf
            out.append(
                RawRoute(
                    name="Principal" if i == 0 else f"Alternativa {i}",
                    provider="graphhopper",
                    geometry=coords,
                    distance_km=round(path["distance"] / 1000, 2),
                    duration_min=round(path["time"] / 60000, 1),
                    surface_by_point=surface_by_point,
                    elevations=elevations,
                )
            )
        return out

    async def route_via(self, origin, waypoint, dest, vehicle_id, client):
        body = {
            "points": [[origin[1], origin[0]], [waypoint[1], waypoint[0]],
                       [dest[1], dest[0]]],
            "profile": self.profile,
            "elevation": True,
            "points_encoded": False,
            "details": ["surface", "toll", "road_class"],
            "instructions": False,
        }
        custom_model = self._request_custom_model(vehicle_id)
        if custom_model:
            body["custom_model"] = custom_model
            body["ch.disable"] = True
        params = {"key": self.api_key} if self.api_key else {}
        try:
            r = await client.post(
                f"{self.base_url}/route", json=body, params=params, timeout=45
            )
            r.raise_for_status()
            paths = r.json().get("paths", [])
            if not paths:
                return None
            path = paths[0]
            raw_coords = path["points"]["coordinates"]
            coords = [[c[1], c[0]] for c in raw_coords]
            elevations = (
                [c[2] for c in raw_coords] if raw_coords and len(raw_coords[0]) >= 3 else None
            )
            surface_by_point: dict[int, Surface] = {}
            for start, end, value in path.get("details", {}).get("surface", []):
                surf = OSM_SURFACE_MAP.get(str(value), Surface.UNKNOWN)
                for idx in range(start, end):
                    surface_by_point[idx] = surf
            return RawRoute(
                name="Alternativa", provider="graphhopper", geometry=coords,
                distance_km=round(path["distance"] / 1000, 2),
                duration_min=round(path["time"] / 60000, 1),
                surface_by_point=surface_by_point, elevations=elevations,
            )
        except (httpx.HTTPError, KeyError, ValueError):
            return None


def provider_for_tenant(tenant) -> RoutingProvider:
    if tenant.graphhopper_url:
        return GraphHopperProvider(
            tenant.graphhopper_url, tenant.graphhopper_key, tenant=tenant
        )
    return OSRMProvider(tenant.osrm_base_url)
