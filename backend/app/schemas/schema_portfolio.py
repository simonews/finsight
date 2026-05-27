import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PortfolioBase(BaseModel):
    name: str
    description: str | None = None


class PortfolioCreate(PortfolioBase):
    pass


class PortfolioUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class PortfolioRead(PortfolioBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime