import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.db.url import get_async_database_url
from app.models.market_data import MarketDataSnapshot


async def _store_snapshot(ticker: str) -> None:
    engine = create_async_engine(get_async_database_url(), poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            snapshot = MarketDataSnapshot(
                ticker=ticker,
                raw_payload={
                    "ticker": ticker,
                    "price": 123.45,
                    "currency": "USD",
                    "source": "mock",
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            session.add(snapshot)
            await session.commit()
    finally:
        await engine.dispose()


@celery_app.task(name="fetch_market_data_task")
def fetch_market_data_task(ticker: str) -> dict[str, str]:
    time.sleep(5)
    asyncio.run(_store_snapshot(ticker))
    return {"ticker": ticker, "status": "stored"}