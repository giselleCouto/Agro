"""Router: Onboarding de Nova Região"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from ..core.database import get_db
from ..models.client import Client
from ..models.plant import Plant
from ..schemas.onboarding import OnboardingRequest, OnboardingStatus
from ..services.onboarding_service import OnboardingService

router = APIRouter()


@router.post("/new-region", response_model=OnboardingStatus)
async def onboard_new_region(
    request: OnboardingRequest,
    background_tasks: BackgroundTasks,
    shapefile: UploadFile = File(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Onboarding completo de nova região em 1 passo:
    1. Cria cliente
    2. Cadastra usina
    3. Importa talhões do shapefile (se fornecido)
    4. Detecta zonas urbanas automaticamente (Overpass API)
    5. Detecta pedágios na região (base ANTT)
    6. Download SRTM tiles da região
    7. Calcula todas as rotas

    Passos 4-7 executam em background.
    """
    service = OnboardingService(db)

    # Passos síncronos (rápidos)
    client = await service.create_client(request)
    plant = await service.create_plant(client.id, request)

    fields_count = 0
    if shapefile:
        fields_count = await service.import_shapefile(client.id, shapefile)

    # Passos assíncronos (demorados) em background
    background_tasks.add_task(
        service.run_background_setup,
        client.id, plant.id
    )

    return OnboardingStatus(
        client_id=client.id,
        status="processing",
        steps_completed=["client_created", "plant_created", "fields_imported"] if fields_count > 0 else ["client_created", "plant_created"],
        steps_pending=["detect_urban_zones", "detect_tolls", "download_srtm", "calculate_routes"],
        fields_imported=fields_count,
        message=f"Região '{request.client_name}' criada. {fields_count} talhões importados. Processamento em background iniciado."
    )


@router.get("/status/{client_id}", response_model=OnboardingStatus)
async def get_onboarding_status(client_id: int, db: AsyncSession = Depends(get_db)):
    """Verificar status do onboarding de uma região."""
    client = await db.get(Client, client_id)
    if not client:
        raise HTTPException(404, "Cliente não encontrado")

    service = OnboardingService(db)
    return await service.get_status(client_id)
