"""
CanaRoute - API Principal
Sistema de Otimização de Rotas para Transporte de Cana-de-Açúcar

Versão: 1.0.0
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from contextlib import asynccontextmanager

from .core.config import settings
from .routers import (
    clients,
    plants,
    fields,
    vehicles,
    tolls,
    urban_zones,
    routes,
    economy,
    onboarding,
    way_files,
    health,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup e shutdown do app."""
    # Startup
    print(f"🚀 CanaRoute v{settings.APP_VERSION} iniciando...")
    print(f"   Ambiente: {settings.ENVIRONMENT}")
    print(f"   OSRM: {settings.OSRM_PUBLIC_URL}")
    print(f"   GraphHopper: {settings.GRAPHHOPPER_URL}")
    yield
    # Shutdown
    print("🛑 CanaRoute encerrando...")


app = FastAPI(
    title="CanaRoute API",
    description="""
## Sistema de Otimização de Rotas para Transporte de Cana-de-Açúcar

API REST completa para:
- Gestão de usinas, talhões, veículos, pedágios e zonas urbanas
- Cálculo de rotas otimizadas com restrição de largura de via
- Modelo de consumo de combustível calibrado (peso × inclinação × clima)
- Geração de arquivos WAY compatíveis com Solinftec
- Onboarding de novas regiões com mínimo esforço

### Modelo de Consumo
```
F = (R₀ + α·slope) × distância × PBT × f_clima
```
- R₀ = 0,0030 L/(km·t) — consumo base
- α = 0,0040 L/(km·t·%) — fator de inclinação
- slope clip = 6% — inclinação máxima considerada
- PBT = peso bruto total do veículo (t)
- f_clima = fator climático (1.0 a 1.5)
    """,
    version=settings.APP_VERSION,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, tags=["Health"])
app.include_router(clients.router, prefix="/api/v1/clients", tags=["Clientes"])
app.include_router(plants.router, prefix="/api/v1/plants", tags=["Usinas"])
app.include_router(fields.router, prefix="/api/v1/fields", tags=["Talhões"])
app.include_router(vehicles.router, prefix="/api/v1/vehicles", tags=["Veículos"])
app.include_router(tolls.router, prefix="/api/v1/tolls", tags=["Pedágios"])
app.include_router(urban_zones.router, prefix="/api/v1/urban-zones", tags=["Zonas Urbanas"])
app.include_router(routes.router, prefix="/api/v1/routes", tags=["Rotas"])
app.include_router(economy.router, prefix="/api/v1/economy", tags=["Economia"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["Onboarding"])
app.include_router(way_files.router, prefix="/api/v1/way", tags=["Arquivos WAY"])
