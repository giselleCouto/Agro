"""Router: Rotas (cálculo e consulta)"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.route import Route
from ..models.field import Field
from ..models.plant import Plant
from ..schemas.route import RouteCalculateRequest, RouteResponse, RouteComparisonResponse
from ..services.route_calculator import RouteCalculator

router = APIRouter()


@router.get("/field/{field_id}", response_model=list[RouteResponse])
async def get_routes_for_field(
    field_id: int,
    vehicle_id: int = None,
    db: AsyncSession = Depends(get_db)
):
    """Obter rotas calculadas para um talhão."""
    query = select(Route).where(Route.field_id == field_id)
    if vehicle_id:
        query = query.where(Route.vehicle_id == vehicle_id)
    query = query.order_by(Route.total_cost)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/calculate", response_model=list[RouteResponse])
async def calculate_route(
    request: RouteCalculateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Calcular rota entre talhão e usina.
    Se vehicle_id não for informado, calcula para todos os veículos.
    """
    field = await db.get(Field, request.field_id)
    if not field:
        raise HTTPException(404, "Talhão não encontrado")

    plant = await db.get(Plant, request.plant_id)
    if not plant:
        raise HTTPException(404, "Usina não encontrada")

    calculator = RouteCalculator(db)
    routes = await calculator.calculate(
        field=field,
        plant=plant,
        vehicle_id=request.vehicle_id,
        climate=request.climate,
        occupancy_pct=request.occupancy_pct,
        force_recalculate=request.force_recalculate
    )
    return routes


@router.post("/calculate-all")
async def calculate_all_routes(
    client_id: int,
    plant_id: int,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Calcular rotas para TODOS os talhões ativos de um cliente.
    Executa em background.
    """
    plant = await db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Usina não encontrada")

    fields_result = await db.execute(
        select(Field).where(Field.client_id == client_id, Field.active == True)
    )
    fields = fields_result.scalars().all()

    if not fields:
        raise HTTPException(404, "Nenhum talhão ativo encontrado")

    # Executar em background
    background_tasks.add_task(
        _calculate_all_background, client_id, plant_id, [f.id for f in fields], force
    )

    return {
        "status": "processing",
        "message": f"Calculando rotas para {len(fields)} talhões em background",
        "fields_count": len(fields)
    }


async def _calculate_all_background(client_id: int, plant_id: int, field_ids: list[int], force: bool):
    """Background task para calcular todas as rotas."""
    from ..core.database import async_session
    async with async_session() as db:
        calculator = RouteCalculator(db)
        for field_id in field_ids:
            try:
                field = await db.get(Field, field_id)
                plant = await db.get(Plant, plant_id)
                if field and plant:
                    await calculator.calculate(
                        field=field, plant=plant,
                        force_recalculate=force
                    )
                    await db.commit()
            except Exception as e:
                print(f"Erro ao calcular rota para field {field_id}: {e}")
                await db.rollback()


@router.get("/comparison/{field_id}/{plant_id}", response_model=RouteComparisonResponse)
async def get_route_comparison(
    field_id: int,
    plant_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Obter comparação completa de rotas (GPS vs alternativas) para um talhão."""
    field = await db.get(Field, field_id)
    if not field:
        raise HTTPException(404, "Talhão não encontrado")

    plant = await db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Usina não encontrada")

    # Buscar rotas
    gps_result = await db.execute(
        select(Route).where(
            Route.field_id == field_id,
            Route.plant_id == plant_id,
            Route.route_type == "gps_real"
        )
    )
    gps_route = gps_result.scalar_one_or_none()

    alt_result = await db.execute(
        select(Route).where(
            Route.field_id == field_id,
            Route.plant_id == plant_id,
            Route.route_type == "alternative"
        ).order_by(Route.total_cost)
    )
    alt_routes = alt_result.scalars().all()

    from ..models.farm import Farm
    farm_name = ""
    if field.farm_id:
        farm = await db.get(Farm, field.farm_id)
        farm_name = farm.name if farm else ""

    # Calcular distância
    from math import radians, sin, cos, sqrt, atan2
    lat1, lon1 = radians(field.latitude), radians(field.longitude)
    lat2, lon2 = radians(plant.latitude), radians(plant.longitude)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    dist_km = 6371 * 2 * atan2(sqrt(a), sqrt(1-a))

    best = alt_routes[0] if alt_routes else None
    economy_trip = None
    economy_season = None
    economy_pct = None
    if gps_route and best and gps_route.total_cost and best.total_cost:
        economy_trip = gps_route.total_cost - best.total_cost
        economy_season = economy_trip * 935
        economy_pct = (economy_trip / gps_route.total_cost) * 100 if gps_route.total_cost > 0 else 0

    return RouteComparisonResponse(
        field_name=field.name or f"T{field.code}",
        farm_name=farm_name,
        plant_name=plant.name,
        distance_to_plant_km=round(dist_km, 1),
        gps_route=gps_route,
        alternative_routes=alt_routes,
        best_route=best,
        economy_per_trip=economy_trip,
        economy_per_season=economy_season,
        economy_pct=economy_pct
    )
