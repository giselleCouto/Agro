"""Router: Zonas Urbanas"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.urban_zone import UrbanZone
from ..schemas.urban_zone import UrbanZoneCreate, UrbanZoneResponse

router = APIRouter()


@router.get("/", response_model=list[UrbanZoneResponse])
async def list_urban_zones(client_id: int = None, db: AsyncSession = Depends(get_db)):
    """Listar zonas urbanas de restrição."""
    query = select(UrbanZone).where(UrbanZone.active == True).order_by(UrbanZone.name)
    if client_id:
        query = query.where((UrbanZone.client_id == client_id) | (UrbanZone.client_id.is_(None)))
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=UrbanZoneResponse, status_code=201)
async def create_urban_zone(data: UrbanZoneCreate, db: AsyncSession = Depends(get_db)):
    """Cadastrar zona urbana de restrição."""
    zone = UrbanZone(**data.model_dump())
    db.add(zone)
    await db.flush()
    await db.refresh(zone)
    return zone


@router.post("/auto-detect", response_model=list[UrbanZoneResponse])
async def auto_detect_urban_zones(
    client_id: int,
    lat_min: float, lat_max: float,
    lon_min: float, lon_max: float,
    db: AsyncSession = Depends(get_db)
):
    """
    Detectar automaticamente zonas urbanas via Overpass API (OSM)
    na bounding box especificada.
    """
    from ..services.urban_detector import detect_urban_zones
    zones = await detect_urban_zones(client_id, lat_min, lat_max, lon_min, lon_max, db)
    return zones


@router.delete("/{zone_id}", status_code=204)
async def delete_urban_zone(zone_id: int, db: AsyncSession = Depends(get_db)):
    zone = await db.get(UrbanZone, zone_id)
    if not zone:
        raise HTTPException(404, "Zona urbana não encontrada")
    await db.delete(zone)
