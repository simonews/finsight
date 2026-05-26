from fastapi import APIRouter, status

from app.tasks.market import fetch_market_data_task

router = APIRouter()


@router.post("/fetch/{ticker}", status_code=status.HTTP_202_ACCEPTED)
async def fetch_market_data(ticker: str) -> dict[str, str]:
    task = fetch_market_data_task.delay(ticker)
    return {"task_id": task.id, "ticker": ticker, "status": "accepted"}