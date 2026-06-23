from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClientCreate(BaseModel):
    name: str
    slug: str
    state: str = "SP"


class ClientResponse(BaseModel):
    id: int
    name: str
    slug: str
    state: str
    created_at: datetime
    plant_count: int = 0
    field_count: int = 0

    class Config:
        from_attributes = True


class ClientList(BaseModel):
    clients: list[ClientResponse]
    total: int
