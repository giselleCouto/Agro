"""Modelo: Rota Calculada"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from datetime import datetime
from ..core.database import Base


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"))
    field_id = Column(Integer, ForeignKey("fields.id", ondelete="CASCADE"))
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"))
    route_type = Column(String(20), default="alternative")

    # Geometria
    geometry = Column(Geometry("LINESTRING", srid=4326))
    geometry_geojson = Column(JSONB)
    coordinates = Column(JSONB)

    # Métricas
    distance_km = Column(Float)
    duration_min = Column(Float)
    elevation_gain_m = Column(Float)
    elevation_loss_m = Column(Float)
    avg_slope_pct = Column(Float)
    max_slope_pct = Column(Float)

    # Consumo
    fuel_liters = Column(Float)
    fuel_cost = Column(Float)

    # Pedágios
    toll_count = Column(Integer, default=0)
    toll_cost = Column(Float, default=0)
    toll_plazas_ids = Column(ARRAY(Integer), default=[])

    # Custo total
    total_cost = Column(Float)

    # Classificação de vias
    highway_mix = Column(JSONB, default={})

    # Trafegabilidade
    suitability_score = Column(Integer, default=100)
    trafficability_scores = Column(JSONB, default={})

    # Alertas
    passes_urban_zone = Column(Boolean, default=False)
    urban_zones_crossed = Column(ARRAY(Integer), default=[])

    # Elevação
    elevation_profile = Column(JSONB)

    # Metadados
    calculated_at = Column(DateTime, default=datetime.utcnow)
    valid_until = Column(DateTime)
    source = Column(String(50), default="osrm")

    # Relationships
    field = relationship("Field", back_populates="routes")
    vehicle = relationship("Vehicle", back_populates="routes")
