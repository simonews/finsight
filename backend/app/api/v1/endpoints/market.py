from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, status
from fastapi.concurrency import run_in_threadpool
from fastapi_limiter.depends import RateLimiter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_owned_portfolio
from app.core.celery_app import celery_app
from app.core.quant import build_portfolio_analytics
from app.crud import position as crud_position
from app.db.session import get_session
from app.models.portfolio import Portfolio
from app.models.user import User
from app.tasks.market import fetch_market_data_task, fetch_etf_holdings_task, fetch_dividends_task, fetch_analyst_task

router = APIRouter()


@router.post(
    "/holdings/{ticker}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def request_etf_holdings(
    ticker: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    task = fetch_etf_holdings_task.delay(ticker.upper())
    return {"task_id": task.id, "ticker": ticker.upper(), "status": "accepted"}

@router.post(
    "/fetch/{ticker}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def fetch_market_data(
    ticker: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    task = fetch_market_data_task.delay(ticker)
    return {"task_id": task.id, "ticker": ticker, "status": "accepted"}


@router.get("/status/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, Any]:
    result = AsyncResult(task_id, app=celery_app)
    payload: Any = result.result
    if isinstance(payload, Exception):
        payload = str(payload)
    return {"task_id": task_id, "status": result.status, "result": payload}


@router.get("/prices/{portfolio_id}")
async def get_portfolio_prices(
    portfolio: Annotated[Portfolio, Depends(get_owned_portfolio)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    positions = await crud_position.get_by_portfolio(session, portfolio_id=portfolio.id)
    payload = [
        {
            "ticker": p.ticker,
            "quantity": float(p.quantity),
            "average_price": float(p.average_price),
        }
        for p in positions
    ]
    return await run_in_threadpool(build_portfolio_analytics, payload)

@router.post(
    "/dividends/{ticker}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def request_dividends(
    ticker: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    task = fetch_dividends_task.delay(ticker.upper())
    return {"task_id": task.id, "ticker": ticker.upper(), "status": "accepted"}

@router.post(
    "/analyst/{ticker}",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(RateLimiter(times=30, seconds=60))],
)
async def request_analyst_targets(
    ticker: str,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    task = fetch_analyst_task.delay(ticker.upper())
    return {"task_id": task.id, "ticker": ticker.upper(), "status": "accepted"}