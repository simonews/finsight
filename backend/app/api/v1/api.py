from fastapi import APIRouter

from app.api.v1.endpoints import ai, auth, market, portfolios, positions

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["portfolios"])
api_router.include_router(positions.router, prefix="/positions", tags=["positions"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])