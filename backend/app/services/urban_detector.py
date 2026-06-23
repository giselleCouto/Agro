"""
CanaRoute - Detector Automático de Zonas Urbanas
Usa Overpass API para identificar cidades/vilas na região.
"""
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.config import settings
from ..models.urban_zone import UrbanZone
from ..schemas.urban_zone import UrbanZoneResponse


async def detect_urban_zones(
    client_id: int,
    lat_min: float, lat_max: float,
    lon_min: float, lon_max: float,
    db: AsyncSession
) -> list[UrbanZoneResponse]:
    """
    Detectar zonas urbanas via Overpass API (OSM).
    Busca por: place=city, place=town, place=village na bounding box.
    """
    query = f"""
    [out:json][timeout:60];
    (
      node["place"="city"]({lat_min},{lon_min},{lat_max},{lon_max});
      node["place"="town"]({lat_min},{lon_min},{lat_max},{lon_max});
      node["place"="village"]({lat_min},{lon_min},{lat_max},{lon_max});
    );
    out body;
    """

    async with httpx.AsyncClient(timeout=60) as client_http:
        try:
            resp = await client_http.post(
                settings.OVERPASS_URL,
                data={"data": query}
            )
            if resp.status_code != 200:
                return []

            data = resp.json()
            elements = data.get("elements", [])

            zones = []
            for elem in elements:
                name = elem.get("tags", {}).get("name", "Desconhecido")
                lat = elem.get("lat")
                lon = elem.get("lon")
                place_type = elem.get("tags", {}).get("place", "village")

                # Raio baseado no tipo
                radius = {"city": 5000, "town": 3000, "village": 1500}.get(place_type, 2000)

                # Criar zona urbana
                zone = UrbanZone(
                    client_id=client_id,
                    name=name,
                    latitude=lat,
                    longitude=lon,
                    radius_m=radius,
                    restriction_level="blocked" if place_type in ["city", "town"] else "caution"
                )
                db.add(zone)
                await db.flush()
                await db.refresh(zone)

                zones.append(UrbanZoneResponse(
                    id=zone.id, name=zone.name,
                    latitude=zone.latitude, longitude=zone.longitude,
                    radius_m=zone.radius_m, restriction_level=zone.restriction_level,
                    active=True, created_at=zone.created_at
                ))

            return zones

        except Exception as e:
            print(f"Overpass error: {e}")
            return []
