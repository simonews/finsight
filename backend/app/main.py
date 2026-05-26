from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.v1.api import api_router
from app.db.session import AsyncSessionLocal

app = FastAPI(title="FinSight API")

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(IntegrityError)
async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": "Foreign key violation: referenced resource does not exist"},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        db_status = "unreachable"
    return {"status": "ok", "database": db_status}