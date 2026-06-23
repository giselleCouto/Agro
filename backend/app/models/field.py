"""Modelo: Talhão"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from datetime import datetime
from ..core.database import Base


class Field(Base):
    __tablename__ = "fields"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"))
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="SET NULL"), nullable=True)
    code = Column(String(50))
    name = Column(String(255))
    area_ha = Column(Float)
    centroid = Column(Geometry("POINT", srid=4326))
    boundary = Column(Geometry("MULTIPOLYGON", srid=4326))
    latitude = Column(Float)
    longitude = Column(Float)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="fields")
    farm = relationship("Farm", back_populates="fields")
    routes = relationship("Route", back_populates="field", cascade="all, delete-orphan")
