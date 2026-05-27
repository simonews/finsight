from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user
from app.core.celery_app import celery_app
from app.models.user import User
from app.tasks.market import fetch_market_data_task

router = APIRouter()


@router.post("/fetch/{ticker}", status_code=status.HTTP_202_ACCEPTED)
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