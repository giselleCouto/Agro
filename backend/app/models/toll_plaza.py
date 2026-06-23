"""Modelo: Praça de Pedágio"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from geoalchemy2 import Geometry
from datetime import datetime
from ..core.database import Base


class TollPlaza(Base):
    __tablename__ = "toll_plazas"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=True)
    name = Column(String(255), nullable=False)
    highway = Column(String(50))
    km = Column(Float)
    location = Column(Geometry("POINT", srid=4326))
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    cost_per_axle = Column(Float, nullable=False, default=7.80)
    bidirectional = Column(Boolean, default=True)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
