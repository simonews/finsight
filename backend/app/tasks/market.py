import asyncio
from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.market_provider import fetch_analyst_targets, fetch_ticker_info, fetch_etf_holdings, fetch_dividends, fetch_analyst_targets
from app.db.url import get_async_database_url
from app.models.market_data import MarketDataSnapshot

logger = get_task_logger(__name__)


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
    ticker_info = fetch_ticker_info(ticker)
    if not ticker_info or ticker_info.get("regularMarketPrice") is None:
        raise ValueError(f"Invalid or unknown ticker: {ticker}")
    snapshot_id = asyncio.run(_store_snapshot(ticker, ticker_info))
    return {"message": "Data fetched successfully", "snapshot_id": snapshot_id}

@celery_app.task(name="fetch_etf_holdings_task")
def fetch_etf_holdings_task(ticker: str) -> dict:
    ticker = ticker.upper()
    info = fetch_ticker_info(ticker) or {}
    quote_type = (info.get("quoteType") or "").upper()
    if quote_type not in ("ETF", "MUTUALFUND"):
        return {"status": "success", "ticker": ticker, "holdings": [],
                "message": f"{ticker} non e' un ETF/fondo: nessuna composizione disponibile."}
    holdings = fetch_etf_holdings(ticker)
    if not holdings:
        return {"status": "success", "ticker": ticker, "holdings": [],
                "message": f"Composizione non disponibile per {ticker}."}
    return {"status": "success", "ticker": ticker,
            "name": info.get("longName") or info.get("shortName") or ticker,
            "holdings": holdings}

@celery_app.task(name="fetch_dividends_task")
def fetch_dividends_task(ticker: str) -> dict:
    ticker = ticker.upper()
    dividends = fetch_dividends(ticker)
    if not dividends:
        return {"status": "success", "ticker": ticker, "dividends": [],
                "message": f"Nessuno storico dividendi per {ticker} (il titolo potrebbe non distribuirne)."}
    return {"status": "success", "ticker": ticker, "dividends": dividends}

@celery_app.task(name="fetch_analyst_task")
def fetch_analyst_task(ticker: str) -> dict:
    ticker = ticker.upper()
    analyst = fetch_analyst_targets(ticker)
    if analyst.get("target_mean") is None:
        return {"status": "success", "ticker": ticker, "analyst": None,
                "message": f"Dati analisti non disponibili per {ticker}."}
    return {"status": "success", "ticker": ticker, "analyst": analyst}