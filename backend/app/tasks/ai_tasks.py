import asyncio
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.celery_app import celery_app
from app.core.quant import calculate_portfolio_metrics
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
            quant_input: list[dict[str, Any]] = [
                {"ticker": p.ticker, "quantity": float(p.quantity)}
                for p in positions_orm
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


@celery_app.task(name="analyze_portfolio_task")
def analyze_portfolio_task(portfolio_id: str) -> dict[str, str]:
    return asyncio.run(_run_analysis(uuid.UUID(portfolio_id)))