"""Router: Talhões (com upload de shapefile)"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..core.database import get_db
from ..models.field import Field
from ..models.farm import Farm
from ..schemas.field import FieldCreate, FieldResponse, FieldBulkResponse
from ..services.shapefile_processor import process_shapefile
import tempfile
import os

router = APIRouter()


@router.get("/", response_model=list[FieldResponse])
async def list_fields(
    client_id: int = None,
    active: bool = True,
    limit: int = Query(default=500, le=5000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """Listar talhões. Filtrar por client_id e status."""
    query = select(Field).where(Field.active == active).order_by(Field.id)
    if client_id:
        query = query.where(Field.client_id == client_id)
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    fields = result.scalars().all()

    responses = []
    for f in fields:
        farm_name = None
        if f.farm_id:
            farm = await db.get(Farm, f.farm_id)
            farm_name = farm.name if farm else None
        responses.append(FieldResponse(
            id=f.id, client_id=f.client_id, farm_id=f.farm_id,
            farm_name=farm_name, code=f.code, name=f.name,
            area_ha=f.area_ha, latitude=f.latitude, longitude=f.longitude,
            active=f.active, created_at=f.created_at
        ))
    return responses


@router.post("/", response_model=FieldResponse, status_code=201)
async def create_field(data: FieldCreate, db: AsyncSession = Depends(get_db)):
    """Cadastrar talhão individual."""
    # Buscar ou criar fazenda
    farm_id = None
    if data.farm_name:
        result = await db.execute(
            select(Farm).where(Farm.name == data.farm_name, Farm.client_id == data.client_id)
        )
        farm = result.scalar_one_or_none()
        if not farm:
            farm = Farm(name=data.farm_name, client_id=data.client_id)
            db.add(farm)
            await db.flush()
        farm_id = farm.id

    field = Field(
        client_id=data.client_id, farm_id=farm_id,
        code=data.code, name=data.name, area_ha=data.area_ha,
        latitude=data.latitude, longitude=data.longitude
    )
    db.add(field)
    await db.flush()
    await db.refresh(field)
    return FieldResponse(
        id=field.id, client_id=field.client_id, farm_id=farm_id,
        farm_name=data.farm_name, code=field.code, name=field.name,
        area_ha=field.area_ha, latitude=field.latitude, longitude=field.longitude,
        active=field.active, created_at=field.created_at
    )


@router.post("/upload-shapefile", response_model=FieldBulkResponse, status_code=201)
async def upload_shapefile(
    client_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload de shapefile (.zip contendo .shp, .shx, .dbf, .prj).
    Extrai automaticamente talhões, calcula centroides e cria registros.
    """
    if not file.filename.endswith('.zip'):
        raise HTTPException(400, "Envie um arquivo .zip contendo o shapefile")

    # Salvar arquivo temporário
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = await process_shapefile(tmp_path, client_id, db)
        return result
    finally:
        os.unlink(tmp_path)


@router.get("/{field_id}", response_model=FieldResponse)
async def get_field(field_id: int, db: AsyncSession = Depends(get_db)):
    """Obter detalhes de um talhão."""
    field = await db.get(Field, field_id)
    if not field:
        raise HTTPException(404, "Talhão não encontrado")
    farm_name = None
    if field.farm_id:
        farm = await db.get(Farm, field.farm_id)
        farm_name = farm.name if farm else None
    return FieldResponse(
        id=field.id, client_id=field.client_id, farm_id=field.farm_id,
        farm_name=farm_name, code=field.code, name=field.name,
        area_ha=field.area_ha, latitude=field.latitude, longitude=field.longitude,
        active=field.active, created_at=field.created_at
    )


@router.delete("/{field_id}", status_code=204)
async def delete_field(field_id: int, db: AsyncSession = Depends(get_db)):
    """Excluir talhão."""
    field = await db.get(Field, field_id)
    if not field:
        raise HTTPException(404, "Talhão não encontrado")
    await db.delete(field)
