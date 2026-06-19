import asyncio
import time
import uuid
from typing import Any
import json

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.quant import calculate_portfolio_metrics
from app.core.quant import compute_ticker_trend
from app.core.market_provider import fetch_ticker_news, fetch_ticker_info
from app.crud import ai_report as crud_ai_report
from app.crud import portfolio as crud_portfolio
from app.crud import position as crud_position
from app.db.url import get_async_database_url
from app.schemas.schema_ai_report import AIReportCreate
from app.services.ai_service import GenerativeAIAnalyzer



def _new_engine():
    return create_async_engine(get_async_database_url(), poolclass=NullPool)


async def _run_analysis(portfolio_id: uuid.UUID) -> dict[str, str]:
    read_engine = _new_engine()
    try:
        async with AsyncSession(read_engine, expire_on_commit=False) as session:
            portfolio = await crud_portfolio.get(session, portfolio_id)
            if portfolio is None:
                raise ValueError(f"Portfolio not found: {portfolio_id}")
            positions_orm = await crud_position.get_by_portfolio(
                session, portfolio_id=portfolio_id
            )
            portfolio_data: dict[str, Any] = {
                "id": str(portfolio.id),
                "name": portfolio.name,
                "description": portfolio.description,
                "positions": [
                    {
                        "ticker": p.ticker,
                        "quantity": str(p.quantity),
                        "average_price": str(p.average_price),
                        "sector": p.sector,
                        "market": p.market,
                    }
                    for p in positions_orm
                ],
            }
            aggregated: dict[str, float] = {}
            for p in positions_orm:
                key = p.ticker.upper()
                aggregated[key] = aggregated.get(key, 0.0) + float(p.quantity)
            quant_input: list[dict[str, Any]] = [
                {"ticker": ticker, "quantity": quantity}
                for ticker, quantity in aggregated.items()
            ]
             
    finally:
        await read_engine.dispose()

    metrics = calculate_portfolio_metrics(quant_input)

    analyzer = GenerativeAIAnalyzer()
    report_text = await analyzer.generate_portfolio_report(portfolio_data, metrics)

    write_engine = _new_engine()
    try:
        async with AsyncSession(write_engine, expire_on_commit=False) as session:
            report = await crud_ai_report.create(
                session,
                obj_in=AIReportCreate(
                    portfolio_id=portfolio_id, report_text=report_text
                ),
            )
            report_id = str(report.id)
    finally:
        await write_engine.dispose()

    return {"status": "success", "report_id": report_id}

async def _run_ticker_explanation(trend: dict) -> str:
    analyzer = GenerativeAIAnalyzer()
    return await analyzer.explain_ticker_trend(trend)

async def _run_news_summary(ticker: str, news_items: list[dict]) -> str:
    analyzer = GenerativeAIAnalyzer()
    return await analyzer.summarize_news(ticker, news_items)


@celery_app.task(name="summarize_news_task")
def summarize_news_task(ticker: str) -> dict[str, str]:
    ticker = ticker.upper()
    news_items = fetch_ticker_news(ticker)
    if not news_items:
        return {"status": "success", "ticker": ticker,
                "summary": f"Nessuna notizia recente disponibile per {ticker}."}
    summary = asyncio.run(_run_news_summary(ticker, news_items))
    return {"status": "success", "ticker": ticker, "summary": summary}


@celery_app.task(name="explain_ticker_task")
def explain_ticker_task(ticker: str) -> dict[str, str]:
    trend = compute_ticker_trend(ticker)
    if trend.get("error"):
        raise ValueError(f"No usable market data for ticker: {ticker}")
    analysis = asyncio.run(_run_ticker_explanation(trend))
    return {"status": "success", "ticker": trend["ticker"], "analysis": analysis}


@celery_app.task(name="analyze_portfolio_task")
def analyze_portfolio_task(portfolio_id: str) -> dict[str, str]:
    return asyncio.run(_run_analysis(uuid.UUID(portfolio_id)))

def _parse_peer_candidates(raw: str) -> list[dict]:
    text = (raw or "").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start:end + 1])
    except Exception:
        return []
    return data if isinstance(data, list) else []


async def _run_peer_generation(ticker, name, sector, industry) -> str:
    analyzer = GenerativeAIAnalyzer()
    return await analyzer.suggest_sector_peers(ticker, name, sector, industry)


@celery_app.task(name="suggest_peers_task")
def suggest_peers_task(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper()
    info = fetch_ticker_info(ticker) or {}
    sector = info.get("sector")
    industry = info.get("industry")
    name = info.get("longName") or info.get("shortName") or ticker
    if not sector:
        return {"status": "success", "ticker": ticker, "sector": None, "peers": [],
                "message": f"Settore non disponibile per {ticker}: impossibile suggerire titoli simili."}

    raw = asyncio.run(_run_peer_generation(ticker, name, sector, industry))

    validated: list[dict] = []
    seen = {ticker}
    for cand in _parse_peer_candidates(raw):
        if not isinstance(cand, dict):
            continue
        cand_ticker = str(cand.get("ticker", "")).upper().strip()
        if not cand_ticker or cand_ticker in seen:
            continue
        seen.add(cand_ticker)
        time.sleep(0.3)  # spaziatura per non farsi throttlare da Yahoo sulla raffica
        cand_info = fetch_ticker_info(cand_ticker, retries=1) or {}
        if cand_info.get("regularMarketPrice") is None:
            continue  # ticker inventato/non valido o fallimento persistente -> scartato
        validated.append({
            "ticker": cand_ticker,
            "name": cand_info.get("longName") or cand_info.get("shortName") or cand.get("name") or cand_ticker,
            "sector": cand_info.get("sector"),
            "current_price": cand_info.get("regularMarketPrice"),
            "reason": str(cand.get("reason", ""))[:120],
        })
        if len(validated) >= 6:
            break

    return {"status": "success", "ticker": ticker, "sector": sector, "peers": validated}