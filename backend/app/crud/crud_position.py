import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.position import Position


class CRUDPosition(CRUDBase[Position]):
    async def get_by_portfolio(
        self, db: AsyncSession, *, portfolio_id: uuid.UUID
    ) -> Sequence[Position]:
        result = await db.execute(
            select(Position).where(Position.portfolio_id == portfolio_id)
        )
        return result.scalars().all()


position = CRUDPosition(Position)