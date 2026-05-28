import asyncio
import json
from typing import Any

import yfinance as yf
from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.cache import CACHE_TTL_SECONDS, get_redis_sync
from app.core.celery_app import celery_app
from app.db.url import get_async_database_url
from app.models.market_data import MarketDataSnapshot

logger = get_task_logger(__name__)


def _fetch_ticker_info(ticker: str) -> dict[str, Any]:
    cache_key = f"yf_cache:info:{ticker.upper()}"
    client = get_redis_sync()
    try:
        cached = client.get(cache_key)
        if cached is not None:
            logger.info("yfinance INFO cache HIT for %s", ticker)
            return json.loads(cached)
    except Exception:
        pass
    logger.info("yfinance INFO cache MISS for %s - downloading", ticker)
    info = yf.Ticker(ticker).info
    if info and info.get("regularMarketPrice") is not None:
        try:
            client.set(cache_key, json.dumps(info, default=str), ex=CACHE_TTL_SECONDS)
        except Exception:
            pass
    return info


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
    ticker_info = _fetch_ticker_info(ticker)
    if not ticker_info or ticker_info.get("regularMarketPrice") is None:
        raise ValueError(f"Invalid or unknown ticker: {ticker}")
    snapshot_id = asyncio.run(_store_snapshot(ticker, ticker_info))
    return {"message": "Data fetched successfully", "snapshot_id": snapshot_id}