"""Modelo: Resultado de Economia"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from datetime import datetime
from ..core.database import Base


class EconomyResult(Base):
    __tablename__ = "economy_results"

    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"))
    field_id = Column(Integer, ForeignKey("fields.id", ondelete="CASCADE"))
    plant_id = Column(Integer, ForeignKey("plants.id", ondelete="CASCADE"))
    vehicle_id = Column(Integer, ForeignKey("vehicles.id", ondelete="CASCADE"))
    gps_route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)
    alt_route_id = Column(Integer, ForeignKey("routes.id"), nullable=True)

    fuel_saving_liters = Column(Float)
    fuel_saving_cost = Column(Float)
    toll_difference = Column(Float)
    total_saving_per_trip = Column(Float)
    total_saving_per_season = Column(Float)
    saving_pct = Column(Float)

    climate_scenario = Column(String(20), default="safra_mix")
    occupancy_pct = Column(Float, default=100)
    fuel_price = Column(Float, default=6.0)
    season_trips = Column(Integer, default=935)
    calculated_at = Column(DateTime, default=datetime.utcnow)
