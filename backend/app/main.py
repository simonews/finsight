from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1.api import api_router
from app.db.session import AsyncSessionLocal

app = FastAPI(title="FinSight API")

app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"
    return {"status": "ok", "database": db_status}