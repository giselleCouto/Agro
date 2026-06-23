"""Modelo: Zona Urbana (restrição de passagem)"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from geoalchemy2 import Geometry
from datetime import datetime
from ..core.database import Base


class UrbanZone(Base):
    __tablename__ = "urban_zones"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    name = Column(String(255), nullable=False)
    center = Column(Geometry("POINT", srid=4326))
    boundary = Column(Geometry("POLYGON", srid=4326))
    radius_m = Column(Float, default=2000)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    restriction_level = Column(String(20), default="blocked")
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
