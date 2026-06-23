"""Router: Praças de Pedágio"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.toll_plaza import TollPlaza
from ..schemas.toll import TollPlazaCreate, TollPlazaResponse

router = APIRouter()


@router.get("/", response_model=list[TollPlazaResponse])
async def list_tolls(client_id: int = None, db: AsyncSession = Depends(get_db)):
    """Listar praças de pedágio."""
    query = select(TollPlaza).where(TollPlaza.active == True).order_by(TollPlaza.name)
    if client_id:
        query = query.where((TollPlaza.client_id == client_id) | (TollPlaza.client_id.is_(None)))
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/", response_model=TollPlazaResponse, status_code=201)
async def create_toll(data: TollPlazaCreate, db: AsyncSession = Depends(get_db)):
    """Cadastrar praça de pedágio."""
    toll = TollPlaza(**data.model_dump())
    db.add(toll)
    await db.flush()
    await db.refresh(toll)
    return toll


@router.delete("/{toll_id}", status_code=204)
async def delete_toll(toll_id: int, db: AsyncSession = Depends(get_db)):
    toll = await db.get(TollPlaza, toll_id)
    if not toll:
        raise HTTPException(404, "Pedágio não encontrado")
    await db.delete(toll)
