import os

os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("CELERY_BROKER_URL", "redis://localhost:6379/1")
os.environ.setdefault("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("GROQ_API_KEY", "test-key")


def _test_database_url() -> str:
    explicit = os.environ.get("TEST_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL", "")
    if base:
        head, _, _ = base.rpartition("/")
        return f"{head}/finsight_test"
    return "postgresql://finsight:finsight@localhost:5432/finsight_test"


os.environ["DATABASE_URL"] = _test_database_url()

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.session import get_session
from app.db.url import get_async_database_url
from app.main import app

test_engine = create_async_engine(get_async_database_url(), poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, expire_on_commit=False, autoflush=False
)

_TABLES = "users, portfolios, positions, ai_reports, market_data_snapshots"


@pytest.fixture(scope="session", autouse=True)
def apply_migrations():
    command.upgrade(Config("alembic.ini"), "head")
    yield


async def _override_get_session():
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture(autouse=True)
async def clean_tables():
    async with test_engine.begin() as conn:
        await conn.execute(
            text(f"TRUNCATE TABLE {_TABLES} RESTART IDENTITY CASCADE")
        )
    yield


@pytest_asyncio.fixture
async def async_client():
    app.dependency_overrides[get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(async_client):
    payload = {"email": "user1@test.com", "password": "Password123"}
    await async_client.post("/api/v1/auth/register", json=payload)
    return payload


@pytest_asyncio.fixture
async def token_headers(async_client, test_user):
    response = await async_client.post(
        "/api/v1/auth/login",
        data={"username": test_user["email"], "password": test_user["password"]},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}