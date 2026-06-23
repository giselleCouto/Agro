"""Modelo: Cliente/Região"""
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    state = Column(String(2), default="SP")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    plants = relationship("Plant", back_populates="client", cascade="all, delete-orphan")
    farms = relationship("Farm", back_populates="client", cascade="all, delete-orphan")
    fields = relationship("Field", back_populates="client", cascade="all, delete-orphan")
    vehicles = relationship("Vehicle", back_populates="client")
