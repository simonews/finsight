import asyncio
from typing import Any

import yfinance as yf
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.db.url import get_async_database_url
from app.models.market_data import MarketDataSnapshot


async def _store_snapshot(ticker: str, payload: dict[str, Any]) -> str:
    engine = create_async_engine(get_async_database_url(), poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            snapshot = MarketDataSnapshot(ticker=ticker, raw_payload=payload)
            session.add(snapshot)
            await session.commit()
            await session.refresh(snapshot)
            return str(snapshot.id)
    finally:
        await engine.dispose()


@celery_app.task(name="fetch_market_data_task")
def fetch_market_data_task(ticker: str) -> dict[str, str]:
    ticker_obj = yf.Ticker(ticker)
    ticker_info: dict[str, Any] = ticker_obj.info
    if not ticker_info or ticker_info.get("regularMarketPrice") is None:
        raise ValueError(f"Invalid or unknown ticker: {ticker}")
    snapshot_id = asyncio.run(_store_snapshot(ticker, ticker_info))
    return {"message": "Data fetched successfully", "snapshot_id": snapshot_id}