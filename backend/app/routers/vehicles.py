"""Router: Veículos"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.vehicle import Vehicle
from ..schemas.vehicle import VehicleCreate, VehicleResponse

router = APIRouter()


@router.get("/", response_model=list[VehicleResponse])
async def list_vehicles(client_id: int = None, db: AsyncSession = Depends(get_db)):
    """Listar veículos. Inclui veículos globais (client_id=NULL) e do cliente."""
    query = select(Vehicle).order_by(Vehicle.pbt_tons)
    if client_id:
        query = query.where((Vehicle.client_id == client_id) | (Vehicle.client_id.is_(None)))
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=VehicleResponse, status_code=201)
async def create_vehicle(data: VehicleCreate, db: AsyncSession = Depends(get_db)):
    """Cadastrar novo tipo de veículo."""
    vehicle = Vehicle(**data.model_dump())
    db.add(vehicle)
    await db.flush()
    await db.refresh(vehicle)
    return vehicle


@router.get("/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(vehicle_id: int, db: AsyncSession = Depends(get_db)):
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Veículo não encontrado")
    return vehicle


@router.put("/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(vehicle_id: int, data: VehicleCreate, db: AsyncSession = Depends(get_db)):
    """Atualizar veículo."""
    vehicle = await db.get(Vehicle, vehicle_id)
    if not vehicle:
        raise HTTPException(404, "Veículo não encontrado")
    for key, value in data.model_dump().items():
        setattr(vehicle, key, value)
    await db.flush()
    await db.refresh(vehicle)
    return vehicle
