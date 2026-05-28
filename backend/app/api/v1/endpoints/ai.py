from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_owned_portfolio
from app.crud import ai_report as crud_ai_report
from app.db.session import get_session
from app.models.ai_report import AIReport
from app.models.portfolio import Portfolio
from app.schemas.schema_ai_report import AIReportRead
from app.tasks.ai_tasks import analyze_portfolio_task

router = APIRouter()


@router.post(
    "/report/{portfolio_id}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=3, seconds=60))],
)
async def request_portfolio_report(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
) -> dict[str, str]:
    task = analyze_portfolio_task.delay(str(portfolio.id))
    return {"task_id": task.id, "portfolio_id": str(portfolio.id), "status": "accepted"}


@router.get("/reports/{portfolio_id}", response_model=list[AIReportRead])
async def read_portfolio_reports(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> Sequence[AIReport]:
    return await crud_ai_report.get_by_portfolio(db, portfolio_id=portfolio.id)