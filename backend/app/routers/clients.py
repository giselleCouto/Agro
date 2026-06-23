"""Router: Clientes/Regiões"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..core.database import get_db
from ..models.client import Client
from ..models.plant import Plant
from ..models.field import Field
from ..schemas.client import ClientCreate, ClientResponse, ClientList

router = APIRouter()


@router.get("/", response_model=ClientList)
async def list_clients(db: AsyncSession = Depends(get_db)):
    """Listar todos os clientes/regiões cadastrados."""
    result = await db.execute(select(Client).order_by(Client.name))
    clients = result.scalars().all()
    responses = []
    for c in clients:
        plant_count = await db.scalar(select(func.count()).where(Plant.client_id == c.id))
        field_count = await db.scalar(select(func.count()).where(Field.client_id == c.id))
        responses.append(ClientResponse(
            id=c.id, name=c.name, slug=c.slug, state=c.state,
            created_at=c.created_at, plant_count=plant_count or 0, field_count=field_count or 0
        ))
    return ClientList(clients=responses, total=len(responses))


@router.post("/", response_model=ClientResponse, status_code=201)
async def create_client(data: ClientCreate, db: AsyncSession = Depends(get_db)):
    """Criar novo cliente/região."""
    client = Client(name=data.name, slug=data.slug, state=data.state)
    db.add(client)
    await db.flush()
    await db.refresh(client)
    return ClientResponse(
        id=client.id, name=client.name, slug=client.slug,
        state=client.state, created_at=client.created_at,
        plant_count=0, field_count=0
    )


@router.get("/{client_id}", response_model=ClientResponse)
async def get_client(client_id: int, db: AsyncSession = Depends(get_db)):
    """Obter detalhes de um cliente."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Cliente não encontrado")
    plant_count = await db.scalar(select(func.count()).where(Plant.client_id == client.id))
    field_count = await db.scalar(select(func.count()).where(Field.client_id == client.id))
    return ClientResponse(
        id=client.id, name=client.name, slug=client.slug,
        state=client.state, created_at=client.created_at,
        plant_count=plant_count or 0, field_count=field_count or 0
    )


@router.delete("/{client_id}", status_code=204)
async def delete_client(client_id: int, db: AsyncSession = Depends(get_db)):
    """Excluir cliente e todos os dados associados."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Cliente não encontrado")
    await db.delete(client)
