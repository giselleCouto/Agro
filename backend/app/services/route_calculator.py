"""
CanaRoute - Serviço de Cálculo de Rotas
Pipeline: OSRM/GH → Elevação → Consumo → Pedágio → Trafegabilidade
"""
import httpx
import numpy as np
from math import radians, sin, cos, sqrt, atan2
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.config import settings
from ..models.route import Route
from ..models.vehicle import Vehicle
from ..models.toll_plaza import TollPlaza
from ..models.urban_zone import UrbanZone


class RouteCalculator:
    """Calculadora de rotas com modelo de consumo calibrado."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = httpx.AsyncClient(timeout=settings.OSRM_TIMEOUT)

    async def calculate(self, field, plant, vehicle_id=None, climate="safra_mix",
                        occupancy_pct=100.0, force_recalculate=False):
        """Calcular rotas para um talhão → usina."""
        # Buscar veículos
        if vehicle_id:
            vehicles = [await self.db.get(Vehicle, vehicle_id)]
        else:
            result = await self.db.execute(select(Vehicle).order_by(Vehicle.pbt_tons))
            vehicles = result.scalars().all()

        if not vehicles:
            vehicles = await self._get_default_vehicles()

        routes = []
        for vehicle in vehicles:
            if not vehicle:
                continue

            # Verificar cache
            if not force_recalculate:
                existing = await self.db.execute(
                    select(Route).where(
                        Route.field_id == field.id,
                        Route.plant_id == plant.id,
                        Route.vehicle_id == vehicle.id,
                        Route.route_type == "alternative"
                    )
                )
                cached = existing.scalar_one_or_none()
                if cached:
                    routes.append(cached)
                    continue

            # Calcular rota via OSRM
            route_data = await self._get_osrm_route(
                field.latitude, field.longitude,
                plant.latitude, plant.longitude,
                vehicle
            )

            if not route_data:
                continue

            # Obter elevação
            elevation_profile = await self._get_elevation_profile(route_data["coordinates"])

            # Calcular consumo
            consumption = self._calculate_consumption(
                route_data, elevation_profile, vehicle, climate, occupancy_pct
            )

            # Verificar pedágios
            tolls = await self._check_tolls(route_data["coordinates"], vehicle)

            # Verificar zonas urbanas
            urban_check = await self._check_urban_zones(route_data["coordinates"])

            # Classificar vias
            highway_mix = route_data.get("highway_mix", {"primary": 0.5, "secondary": 0.3, "tertiary": 0.2})

            # Calcular trafegabilidade
            trafficability = self._calculate_trafficability(highway_mix, vehicle)

            # Calcular tempo
            duration = self._calculate_duration(route_data["distance_km"], highway_mix, vehicle)

            # Custo total
            total_cost = consumption["fuel_cost"] + tolls["total_cost"]

            # Criar registro
            route = Route(
                client_id=field.client_id,
                field_id=field.id,
                plant_id=plant.id,
                vehicle_id=vehicle.id,
                route_type="alternative",
                coordinates=route_data["coordinates"],
                distance_km=route_data["distance_km"],
                duration_min=duration,
                elevation_gain_m=elevation_profile.get("gain", 0),
                elevation_loss_m=elevation_profile.get("loss", 0),
                avg_slope_pct=elevation_profile.get("avg_slope", 0),
                max_slope_pct=elevation_profile.get("max_slope", 0),
                fuel_liters=consumption["liters"],
                fuel_cost=consumption["fuel_cost"],
                toll_count=tolls["count"],
                toll_cost=tolls["total_cost"],
                total_cost=total_cost,
                highway_mix=highway_mix,
                suitability_score=trafficability["score"],
                trafficability_scores=trafficability["by_climate"],
                passes_urban_zone=urban_check["passes"],
                urban_zones_crossed=urban_check["zones"],
                elevation_profile=elevation_profile.get("profile", []),
                source="osrm"
            )
            self.db.add(route)
            await self.db.flush()
            await self.db.refresh(route)
            routes.append(route)

        return routes

    async def _get_osrm_route(self, lat1, lon1, lat2, lon2, vehicle):
        """Obter rota via OSRM."""
        base_url = settings.OSRM_URL if settings.USE_LOCAL_OSRM else settings.OSRM_PUBLIC_URL
        url = f"{base_url}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "steps": "true",
            "annotations": "true"
        }

        # Para veículos maiores, tentar rota alternativa
        if vehicle.pbt_tons >= 70:
            params["alternatives"] = "true"

        try:
            resp = await self.client.get(url, params=params)
            if resp.status_code != 200:
                return None

            data = resp.json()
            if data.get("code") != "Ok" or not data.get("routes"):
                return None

            route = data["routes"][0]
            coords = route["geometry"]["coordinates"]
            distance_km = route["distance"] / 1000

            return {
                "coordinates": [[c[1], c[0]] for c in coords],  # [lat, lon]
                "distance_km": round(distance_km, 2),
                "duration_s": route["duration"],
                "highway_mix": self._estimate_highway_mix(distance_km, vehicle)
            }
        except Exception as e:
            print(f"OSRM error: {e}")
            return None

    async def _get_elevation_profile(self, coordinates):
        """Obter perfil altimétrico via opentopodata."""
        if not coordinates:
            return {"gain": 0, "loss": 0, "avg_slope": 0, "max_slope": 0, "profile": []}

        # Amostrar pontos (max 100 para API)
        step = max(1, len(coordinates) // 100)
        sampled = coordinates[::step]
        if sampled[-1] != coordinates[-1]:
            sampled.append(coordinates[-1])

        locations = "|".join([f"{p[0]},{p[1]}" for p in sampled[:100]])

        try:
            resp = await self.client.get(
                f"https://api.opentopodata.org/v1/srtm30m?locations={locations}",
                timeout=30
            )
            if resp.status_code != 200:
                return {"gain": 0, "loss": 0, "avg_slope": 0, "max_slope": 0, "profile": []}

            data = resp.json()
            elevations = [r["elevation"] or 0 for r in data.get("results", [])]

            if len(elevations) < 2:
                return {"gain": 0, "loss": 0, "avg_slope": 0, "max_slope": 0, "profile": []}

            # Calcular métricas
            gain = sum(max(0, elevations[i+1] - elevations[i]) for i in range(len(elevations)-1))
            loss = sum(max(0, elevations[i] - elevations[i+1]) for i in range(len(elevations)-1))

            # Slopes
            slopes = []
            for i in range(len(sampled) - 1):
                if i < len(elevations) - 1:
                    dist = self._haversine(sampled[i][0], sampled[i][1], sampled[i+1][0], sampled[i+1][1])
                    if dist > 0:
                        slope = abs(elevations[i+1] - elevations[i]) / (dist * 1000) * 100
                        slopes.append(min(slope, settings.FUEL_SLOPE_CLIP))

            avg_slope = np.mean(slopes) if slopes else 0
            max_slope = max(slopes) if slopes else 0

            # Profile para visualização
            profile = [{"dist_km": i * step * 0.01, "elev": e} for i, e in enumerate(elevations)]

            return {
                "gain": round(gain, 1),
                "loss": round(loss, 1),
                "avg_slope": round(avg_slope, 2),
                "max_slope": round(max_slope, 2),
                "profile": profile
            }
        except Exception as e:
            print(f"Elevation error: {e}")
            return {"gain": 0, "loss": 0, "avg_slope": 0, "max_slope": 0, "profile": []}

    def _calculate_consumption(self, route_data, elevation, vehicle, climate, occupancy_pct):
        """Modelo de consumo: F = (R₀ + α·slope) × distância × PBT × f_clima"""
        distance = route_data["distance_km"]
        slope = min(elevation.get("avg_slope", 0), settings.FUEL_SLOPE_CLIP)
        pbt = vehicle.pbt_tons * (occupancy_pct / 100)
        f_clima = settings.CLIMATE_FACTORS.get(climate, 1.0)

        # Ida (carregado)
        r0 = vehicle.fuel_r0 if vehicle.fuel_r0 else settings.FUEL_R0
        alpha = vehicle.fuel_alpha if vehicle.fuel_alpha else settings.FUEL_ALPHA

        fuel_ida = (r0 + alpha * slope) * distance * pbt * f_clima

        # Volta (vazio - 40% do PBT como tara)
        pbt_vazio = vehicle.pbt_tons * 0.40
        fuel_volta = (r0 + alpha * slope) * distance * pbt_vazio * f_clima

        total_liters = fuel_ida + fuel_volta
        fuel_cost = total_liters * settings.FUEL_PRICE

        return {
            "liters": round(total_liters, 2),
            "liters_ida": round(fuel_ida, 2),
            "liters_volta": round(fuel_volta, 2),
            "fuel_cost": round(fuel_cost, 2)
        }

    async def _check_tolls(self, coordinates, vehicle):
        """Verificar se rota cruza praças de pedágio."""
        result = await self.db.execute(
            select(TollPlaza).where(TollPlaza.active == True)
        )
        toll_plazas = result.scalars().all()

        crossed = []
        total_cost = 0

        for plaza in toll_plazas:
            # Verificar proximidade (500m)
            for coord in coordinates[::10]:  # Amostrar a cada 10 pontos
                dist = self._haversine(coord[0], coord[1], plaza.latitude, plaza.longitude)
                if dist < 0.5:  # 500m
                    cost = plaza.cost_per_axle * vehicle.axles
                    if plaza.bidirectional:
                        cost *= 2  # ida e volta
                    crossed.append({"id": plaza.id, "name": plaza.name, "cost": cost})
                    total_cost += cost
                    break

        return {
            "count": len(crossed),
            "plazas": crossed,
            "total_cost": round(total_cost, 2)
        }

    async def _check_urban_zones(self, coordinates):
        """Verificar se rota passa por zonas urbanas."""
        result = await self.db.execute(
            select(UrbanZone).where(UrbanZone.active == True)
        )
        zones = result.scalars().all()

        crossed = []
        for zone in zones:
            radius_km = zone.radius_m / 1000
            for coord in coordinates[::5]:
                dist = self._haversine(coord[0], coord[1], zone.latitude, zone.longitude)
                if dist < radius_km:
                    crossed.append(zone.id)
                    break

        return {"passes": len(crossed) > 0, "zones": crossed}

    def _calculate_trafficability(self, highway_mix, vehicle):
        """Score de trafegabilidade por cenário climático."""
        # Pesos por tipo de via e veículo
        road_scores = {
            "primary": {"seco": 100, "umido": 98, "molhado": 95, "enlameado": 90, "severo": 85},
            "secondary": {"seco": 100, "umido": 95, "molhado": 90, "enlameado": 80, "severo": 70},
            "tertiary": {"seco": 95, "umido": 85, "molhado": 75, "enlameado": 60, "severo": 45},
            "unclassified": {"seco": 85, "umido": 70, "molhado": 55, "enlameado": 35, "severo": 20},
            "track": {"seco": 70, "umido": 50, "molhado": 30, "enlameado": 10, "severo": 0},
        }

        # Penalidade por veículo em vias estreitas
        vehicle_penalty = 1.0
        if vehicle.pbt_tons >= 90:
            vehicle_penalty = 0.7
        elif vehicle.pbt_tons >= 70:
            vehicle_penalty = 0.85

        by_climate = {}
        for climate in ["seco", "umido", "molhado", "enlameado", "severo"]:
            score = 0
            total_weight = 0
            for road_type, pct in highway_mix.items():
                if road_type in road_scores:
                    base = road_scores[road_type][climate]
                    score += base * pct * vehicle_penalty
                    total_weight += pct
            if total_weight > 0:
                by_climate[climate] = round(score / total_weight)
            else:
                by_climate[climate] = 50

        # Score geral (safra-mix)
        overall = round(
            by_climate.get("seco", 100) * 0.50 +
            by_climate.get("umido", 85) * 0.30 +
            by_climate.get("molhado", 65) * 0.15 +
            by_climate.get("enlameado", 40) * 0.05
        )

        return {"score": overall, "by_climate": by_climate}

    def _calculate_duration(self, distance_km, highway_mix, vehicle):
        """Calcular tempo estimado de viagem (ida+volta em minutos)."""
        speeds = vehicle.speed_by_road_class or {
            "primary": 60, "secondary": 50, "tertiary": 40,
            "unclassified": 30, "track": 20
        }

        # Velocidade média ponderada
        avg_speed = 0
        total_weight = 0
        for road_type, pct in highway_mix.items():
            if road_type in speeds:
                avg_speed += speeds[road_type] * pct
                total_weight += pct

        if total_weight > 0:
            avg_speed /= total_weight
        else:
            avg_speed = 40

        # Tempo ida + volta
        duration_ida = (distance_km / avg_speed) * 60  # minutos
        duration_volta = (distance_km / (avg_speed * 1.1)) * 60  # volta vazio = 10% mais rápido

        return round(duration_ida + duration_volta, 1)

    def _estimate_highway_mix(self, distance_km, vehicle):
        """Estimar composição de vias baseado na distância e tipo de veículo."""
        if distance_km > 40:
            return {"primary": 0.50, "secondary": 0.30, "tertiary": 0.15, "unclassified": 0.05}
        elif distance_km > 20:
            return {"primary": 0.30, "secondary": 0.35, "tertiary": 0.25, "unclassified": 0.10}
        else:
            return {"secondary": 0.25, "tertiary": 0.40, "unclassified": 0.25, "track": 0.10}

    async def _get_default_vehicles(self):
        """Retornar veículos padrão se nenhum cadastrado."""
        result = await self.db.execute(select(Vehicle).order_by(Vehicle.pbt_tons))
        return result.scalars().all()

    @staticmethod
    def _haversine(lat1, lon1, lat2, lon2):
        """Distância haversine em km."""
        R = 6371
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
        return R * 2 * atan2(sqrt(a), sqrt(1-a))
