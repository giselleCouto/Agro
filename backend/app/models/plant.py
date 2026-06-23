"""Modelo: Usina"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry
from datetime import datetime
from ..core.database import Base


class Plant(Base):
    __tablename__ = "plants"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    code = Column(String(50))
    location = Column(Geometry("POINT", srid=4326))
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    capacity_tons_day = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="plants")
