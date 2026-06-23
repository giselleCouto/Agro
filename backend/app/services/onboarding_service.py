"""
CanaRoute - Serviço de Onboarding
Automatiza setup de nova região com mínimo esforço.
"""
import tempfile
import os
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..models.client import Client
from ..models.plant import Plant
from ..models.field import Field
from ..models.urban_zone import UrbanZone
from ..models.toll_plaza import TollPlaza
from ..models.route import Route
from ..schemas.onboarding import OnboardingRequest, OnboardingStatus
from .shapefile_processor import process_shapefile
from .urban_detector import detect_urban_zones
from .route_calculator import RouteCalculator


class OnboardingService:
    """Serviço de onboarding de nova região."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_client(self, request: OnboardingRequest) -> Client:
        """Criar cliente/região."""
        client = Client(
            name=request.client_name,
            slug=request.client_slug,
            state=request.state
        )
        self.db.add(client)
        await self.db.flush()
        await self.db.refresh(client)
        return client

    async def create_plant(self, client_id: int, request: OnboardingRequest) -> Plant:
        """Criar usina."""
        plant = Plant(
            client_id=client_id,
            name=request.plant_name,
            latitude=request.plant_latitude,
            longitude=request.plant_longitude,
            capacity_tons_day=request.plant_capacity
        )
        self.db.add(plant)
        await self.db.flush()
        await self.db.refresh(plant)
        return plant

    async def import_shapefile(self, client_id: int, shapefile: UploadFile) -> int:
        """Importar talhões de shapefile."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            content = await shapefile.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            result = await process_shapefile(tmp_path, client_id, self.db)
            return result.fields_created
        finally:
            os.unlink(tmp_path)

    async def run_background_setup(self, client_id: int, plant_id: int):
        """
        Executar setup em background:
        1. Detectar zonas urbanas
        2. Detectar pedágios (futuro: base ANTT)
        3. Calcular rotas para todos os talhões
        """
        from ..core.database import async_session

        async with async_session() as db:
            try:
                # 1. Detectar bounding box dos talhões
                fields_result = await db.execute(
                    select(Field).where(Field.client_id == client_id, Field.active == True)
                )
                fields = fields_result.scalars().all()

                if not fields:
                    return

                lats = [f.latitude for f in fields]
                lons = [f.longitude for f in fields]
                lat_min, lat_max = min(lats) - 0.1, max(lats) + 0.1
                lon_min, lon_max = min(lons) - 0.1, max(lons) + 0.1

                # 2. Detectar zonas urbanas
                await detect_urban_zones(client_id, lat_min, lat_max, lon_min, lon_max, db)
                await db.commit()

                # 3. Calcular rotas
                plant = await db.get(Plant, plant_id)
                calculator = RouteCalculator(db)

                for field in fields:
                    try:
                        await calculator.calculate(field=field, plant=plant)
                        await db.commit()
                    except Exception as e:
                        print(f"Route calc error for field {field.id}: {e}")
                        await db.rollback()

            except Exception as e:
                print(f"Background setup error: {e}")
                await db.rollback()

    async def get_status(self, client_id: int) -> OnboardingStatus:
        """Obter status do onboarding."""
        fields_count = await self.db.scalar(
            select(func.count()).where(Field.client_id == client_id)
        )
        routes_count = await self.db.scalar(
            select(func.count()).where(Route.client_id == client_id)
        )
        zones_count = await self.db.scalar(
            select(func.count()).where(UrbanZone.client_id == client_id)
        )
        tolls_count = await self.db.scalar(
            select(func.count()).where(TollPlaza.client_id == client_id)
        )

        steps_completed = ["client_created", "plant_created"]
        steps_pending = []

        if fields_count > 0:
            steps_completed.append("fields_imported")
        if zones_count > 0:
            steps_completed.append("urban_zones_detected")
        else:
            steps_pending.append("detect_urban_zones")
        if routes_count > 0:
            steps_completed.append("routes_calculated")
        else:
            steps_pending.append("calculate_routes")

        status = "completed" if not steps_pending else "processing"

        return OnboardingStatus(
            client_id=client_id,
            status=status,
            steps_completed=steps_completed,
            steps_pending=steps_pending,
            fields_imported=fields_count or 0,
            routes_calculated=routes_count or 0,
            urban_zones_detected=zones_count or 0,
            toll_plazas_detected=tolls_count or 0,
            message=f"{'Processamento completo' if status == 'completed' else 'Processamento em andamento'}"
        )
