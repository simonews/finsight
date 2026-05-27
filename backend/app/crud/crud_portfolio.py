import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.portfolio import Portfolio
from app.schemas.schema_portfolio import PortfolioCreate, PortfolioUpdate


class CRUDPortfolio(CRUDBase[Portfolio, PortfolioCreate, PortfolioUpdate]):
    async def create_with_owner(
        self, db: AsyncSession, *, obj_in: PortfolioCreate, owner_id: uuid.UUID
    ) -> Portfolio:
        db_obj = Portfolio(**obj_in.model_dump(), user_id=owner_id)
        db.add(db_obj)
        await db.commit()
        await db.refresh(db_obj)
        return db_obj

    async def get_by_owner(
        self, db: AsyncSession, *, owner_id: uuid.UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[Portfolio]:
        result = await db.execute(
            select(Portfolio)
            .where(Portfolio.user_id == owner_id)
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()


portfolio = CRUDPortfolio(Portfolio)