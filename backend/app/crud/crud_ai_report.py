import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.base import CRUDBase
from app.models.ai_report import AIReport
from app.schemas.schema_ai_report import AIReportCreate


class CRUDAIReport(CRUDBase[AIReport, AIReportCreate, AIReportCreate]):
    async def get_by_portfolio(
        self, db: AsyncSession, *, portfolio_id: uuid.UUID
    ) -> Sequence[AIReport]:
        result = await db.execute(
            select(AIReport)
            .where(AIReport.portfolio_id == portfolio_id)
            .order_by(AIReport.generated_at.desc())
        )
        return result.scalars().all()


ai_report = CRUDAIReport(AIReport)