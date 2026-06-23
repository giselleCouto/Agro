"""Modelo: Fazenda"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from ..core.database import Base


class Farm(Base):
    __tablename__ = "farms"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"))
    name = Column(String(255), nullable=False)
    code = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="farms")
    fields = relationship("Field", back_populates="farm")
