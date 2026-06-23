"""Router: Economia"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..core.database import get_db
from ..models.route import Route
from ..models.field import Field
from ..models.farm import Farm
from ..models.vehicle import Vehicle
from ..models.client import Client
from ..schemas.economy import EconomyResponse, EconomySummary

router = APIRouter()


@router.get("/summary/{client_id}", response_model=EconomySummary)
async def get_economy_summary(client_id: int, db: AsyncSession = Depends(get_db)):
    """Resumo de economia para um cliente."""
    client = await db.get(Client, client_id)
    if not client:
        from fastapi import HTTPException
        raise HTTPException(404, "Cliente não encontrado")

    # Buscar todos os campos com rotas
    fields_result = await db.execute(
        select(Field).where(Field.client_id == client_id, Field.active == True)
    )
    all_fields = fields_result.scalars().all()

    total_saving = 0
    fields_with_economy = 0
    best_field = None
    best_saving = 0

    for field in all_fields:
        # GPS route
        gps = await db.execute(
            select(Route).where(
                Route.field_id == field.id, Route.route_type == "gps_real"
            )
        )
        gps_route = gps.scalar_one_or_none()

        # Best alternative
        alt = await db.execute(
            select(Route).where(
                Route.field_id == field.id, Route.route_type == "alternative"
            ).order_by(Route.total_cost).limit(1)
        )
        alt_route = alt.scalar_one_or_none()

        if gps_route and alt_route and gps_route.total_cost and alt_route.total_cost:
            saving = gps_route.total_cost - alt_route.total_cost
            if saving > 0:
                fields_with_economy += 1
                season_saving = saving * 935
                total_saving += season_saving
                if season_saving > best_saving:
                    best_saving = season_saving
                    best_field = field.name or f"T{field.code}"

    avg_pct = (total_saving / (len(all_fields) * 935 * 200)) * 100 if all_fields else 0

    return EconomySummary(
        client_id=client_id,
        client_name=client.name,
        total_fields=len(all_fields),
        fields_with_economy=fields_with_economy,
        fields_without_economy=len(all_fields) - fields_with_economy,
        total_saving_per_season=round(total_saving, 2),
        avg_saving_pct=round(avg_pct, 1),
        best_field=best_field,
        best_saving=round(best_saving, 2)
    )


@router.get("/details/{client_id}", response_model=list[EconomyResponse])
async def get_economy_details(
    client_id: int,
    vehicle_slug: str = "treminhao",
    climate: str = "safra_mix",
    db: AsyncSession = Depends(get_db)
):
    """Detalhamento de economia por talhão."""
    # Buscar veículo
    vehicle_result = await db.execute(
        select(Vehicle).where(Vehicle.slug == vehicle_slug)
    )
    vehicle = vehicle_result.scalar_one_or_none()
    if not vehicle:
        return []

    fields_result = await db.execute(
        select(Field).where(Field.client_id == client_id, Field.active == True)
    )
    all_fields = fields_result.scalars().all()

    results = []
    for field in all_fields:
        gps = await db.execute(
            select(Route).where(
                Route.field_id == field.id,
                Route.vehicle_id == vehicle.id,
                Route.route_type == "gps_real"
            )
        )
        gps_route = gps.scalar_one_or_none()

        alt = await db.execute(
            select(Route).where(
                Route.field_id == field.id,
                Route.vehicle_id == vehicle.id,
                Route.route_type == "alternative"
            ).order_by(Route.total_cost).limit(1)
        )
        alt_route = alt.scalar_one_or_none()

        if gps_route and alt_route and gps_route.total_cost and alt_route.total_cost:
            saving = gps_route.total_cost - alt_route.total_cost
            farm_name = ""
            if field.farm_id:
                farm = await db.get(Farm, field.farm_id)
                farm_name = farm.name if farm else ""

            results.append(EconomyResponse(
                field_id=field.id,
                field_name=field.name or f"T{field.code}",
                farm_name=farm_name,
                vehicle_name=vehicle.name,
                gps_cost=round(gps_route.total_cost, 2),
                alt_cost=round(alt_route.total_cost, 2),
                saving_per_trip=round(saving, 2),
                saving_per_season=round(saving * 935, 2),
                saving_pct=round((saving / gps_route.total_cost) * 100, 1) if gps_route.total_cost > 0 else 0,
                climate=climate
            ))

    return sorted(results, key=lambda x: x.saving_per_season, reverse=True)
