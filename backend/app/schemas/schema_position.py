import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PositionBase(BaseModel):
    ticker: str
    quantity: Decimal
    average_price: Decimal
    purchase_date: datetime
    sector: str | None = None
    market: str | None = None


class PositionCreate(PositionBase):
    # annidato in PortfolioCreate -> serve per coerenza con gli altri schemi
    portfolio_id: uuid.UUID


class PositionUpdate(BaseModel):
    ticker: str | None = None
    quantity: Decimal | None = None
    average_price: Decimal | None = None
    purchase_date: datetime | None = None
    sector: str | None = None
    market: str | None = None


class PositionRead(PositionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    portfolio_id: uuid.UUID