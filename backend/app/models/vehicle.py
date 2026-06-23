"""Modelo: Veículo"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class Vehicle(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(100), nullable=False)
    slug = Column(String(50), nullable=False)
    pbt_tons = Column(Float, nullable=False)
    axles = Column(Integer, nullable=False)
    length_m = Column(Float, nullable=False)
    width_m = Column(Float, nullable=False)
    min_road_class = Column(String(20), default="tertiary")
    caution_road_classes = Column(ARRAY(String), default=[])
    blocked_road_classes = Column(ARRAY(String), default=[])
    speed_by_road_class = Column(JSONB, default={})
    fuel_r0 = Column(Float, default=0.0030)
    fuel_alpha = Column(Float, default=0.0040)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="vehicles")
    routes = relationship("Route", back_populates="vehicle")
