"""Router: Usinas"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.plant import Plant
from ..schemas.plant import PlantCreate, PlantResponse

router = APIRouter()


@router.get("/", response_model=list[PlantResponse])
async def list_plants(client_id: int = None, db: AsyncSession = Depends(get_db)):
    """Listar usinas. Filtrar por client_id opcional."""
    query = select(Plant).order_by(Plant.name)
    if client_id:
        query = query.where(Plant.client_id == client_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=PlantResponse, status_code=201)
async def create_plant(data: PlantCreate, db: AsyncSession = Depends(get_db)):
    """Cadastrar nova usina."""
    plant = Plant(
        client_id=data.client_id,
        name=data.name,
        code=data.code,
        latitude=data.latitude,
        longitude=data.longitude,
        capacity_tons_day=data.capacity_tons_day
    )
    db.add(plant)
    await db.flush()
    await db.refresh(plant)
    return plant


@router.get("/{plant_id}", response_model=PlantResponse)
async def get_plant(plant_id: int, db: AsyncSession = Depends(get_db)):
    """Obter detalhes de uma usina."""
    plant = await db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Usina não encontrada")
    return plant


@router.delete("/{plant_id}", status_code=204)
async def delete_plant(plant_id: int, db: AsyncSession = Depends(get_db)):
    """Excluir usina."""
    plant = await db.get(Plant, plant_id)
    if not plant:
        raise HTTPException(404, "Usina não encontrada")
    await db.delete(plant)
