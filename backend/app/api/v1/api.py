from fastapi import APIRouter

from app.api.v1.endpoints import market, portfolios, positions

api_router = APIRouter()
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["portfolios"])
api_router.include_router(positions.router, prefix="/positions", tags=["positions"])
api_router.include_router(market.router, prefix="/market", tags=["market"])