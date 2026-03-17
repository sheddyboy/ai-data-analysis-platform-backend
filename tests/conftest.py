"""Pytest configuration and shared fixtures for integration tests."""

import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from typing import AsyncGenerator

from app.main import app
from app.database import Base, get_db

# In-memory SQLite for tests (no Postgres needed)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    """Create all tables before the test session; drop them after."""
    # Import all models so Base knows about them
    import app.models.user  # noqa: F401
    import app.models.dataset  # noqa: F401
    import app.models.session  # noqa: F401
    import app.models.user_quota  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client wired to the test app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:  # type: ignore[arg-type]
        yield ac


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient) -> dict:
    """Register a user and return Authorization headers."""
    await client.post("/api/v1/auth/register", json={"email": "test@example.com", "password": "password123"})
    resp = await client.post("/api/v1/auth/login", json={"email": "test@example.com", "password": "password123"})
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
