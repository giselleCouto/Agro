"""
CanaRoute - Configuração Central
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Configurações do sistema carregadas de variáveis de ambiente."""

    # App
    APP_NAME: str = "CanaRoute"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://canaroute:canaroute_secret@localhost:5432/canaroute"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    ROUTE_CACHE_TTL: int = 86400  # 24h

    # Auth
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480

    # Roteamento
    OSRM_URL: str = "http://localhost:5000"
    OSRM_PUBLIC_URL: str = "http://router.project-osrm.org"
    GRAPHHOPPER_URL: str = "http://localhost:8989"
    USE_LOCAL_OSRM: bool = False
    OSRM_TIMEOUT: int = 30

    # Elevação SRTM
    SRTM_DATA_DIR: str = "/app/data/srtm"
    SRTM_RESOLUTION: int = 30  # metros

    # Modelo de Consumo
    FUEL_R0: float = 0.0030  # L/(km·t) base
    FUEL_ALPHA: float = 0.0040  # L/(km·t·%) slope factor
    FUEL_SLOPE_CLIP: float = 6.0  # % max slope
    FUEL_PRICE: float = 6.00  # R$/L

    # Clima
    CLIMATE_FACTORS: dict = {
        "seco": 1.00,
        "umido": 1.08,
        "molhado": 1.15,
        "enlameado": 1.30,
        "severo": 1.50,
        "safra_mix": 1.069
    }

    # Safra
    SAFRA_DAYS: int = 220
    SAFRA_AVAILABILITY: float = 0.85
    TRIPS_PER_DAY: int = 5

    # Overpass API
    OVERPASS_URL: str = "https://overpass-api.de/api/interpreter"
    OVERPASS_TIMEOUT: int = 60

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
