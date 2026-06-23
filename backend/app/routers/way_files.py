"""Router: Geração de Arquivos WAY (Solinftec)"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.route import Route
from ..models.field import Field
from ..models.vehicle import Vehicle
from ..models.farm import Farm
from ..services.way_generator import WayGenerator
import io

router = APIRouter()


@router.get("/{route_id}", response_class=PlainTextResponse)
async def generate_way_file(route_id: int, db: AsyncSession = Depends(get_db)):
    """Gerar arquivo WAY para uma rota específica."""
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(404, "Rota não encontrada")

    field = await db.get(Field, route.field_id)
    vehicle = await db.get(Vehicle, route.vehicle_id)

    generator = WayGenerator()
    content = generator.generate_way(route, field, vehicle)

    return PlainTextResponse(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f"attachment; filename=CANAROUTE_{vehicle.slug}_{field.code}.way"}
    )


@router.get("/{route_id}/gpx")
async def generate_gpx_file(route_id: int, db: AsyncSession = Depends(get_db)):
    """Gerar arquivo GPX para uma rota específica."""
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(404, "Rota não encontrada")

    field = await db.get(Field, route.field_id)
    vehicle = await db.get(Vehicle, route.vehicle_id)

    generator = WayGenerator()
    content = generator.generate_gpx(route, field, vehicle)

    return PlainTextResponse(
        content=content,
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f"attachment; filename=CANAROUTE_{vehicle.slug}_{field.code}.gpx"}
    )


@router.get("/{route_id}/kml")
async def generate_kml_file(route_id: int, db: AsyncSession = Depends(get_db)):
    """Gerar arquivo KML para uma rota específica."""
    route = await db.get(Route, route_id)
    if not route:
        raise HTTPException(404, "Rota não encontrada")

    field = await db.get(Field, route.field_id)
    vehicle = await db.get(Vehicle, route.vehicle_id)

    generator = WayGenerator()
    content = generator.generate_kml(route, field, vehicle)

    return PlainTextResponse(
        content=content,
        media_type="application/vnd.google-earth.kml+xml",
        headers={"Content-Disposition": f"attachment; filename=CANAROUTE_{vehicle.slug}_{field.code}.kml"}
    )
