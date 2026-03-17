"""Integration tests for the v5 monthly token quota system."""

from datetime import datetime, timezone, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user_quota import UserQuota
from app.models.user import User
from tests.conftest import TestSessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def quota_client(client: AsyncClient) -> AsyncClient:
    """Return the standard test client (alias for clarity)."""
    return client


@pytest_asyncio.fixture
async def quota_auth_headers(client: AsyncClient) -> dict:
    """Register a fresh user and return auth headers."""
    email = "quota_user@example.com"
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "password123"}
    )
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "password123"}
    )
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Helper: get quota row from DB
# ---------------------------------------------------------------------------


async def _get_quota_for_email(email: str) -> UserQuota | None:
    async with TestSessionLocal() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        if user is None:
            return None
        quota_result = await session.execute(
            select(UserQuota).where(UserQuota.user_id == user.id)
        )
        return quota_result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_quota_unauthenticated(client: AsyncClient):
    """GET /quota/me without a token should return 401."""
    resp = await client.get("/api/v1/quota/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_quota_creates_row(client: AsyncClient, quota_auth_headers: dict):
    """First call to /quota/me should lazily create a quota row and return defaults."""
    resp = await client.get("/api/v1/quota/me", headers=quota_auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["tokens_used"] == 0
    assert data["monthly_limit"] == 500_000
    assert data["remaining"] == 500_000
    assert data["percentage_used"] == 0.0
    assert "period_end" in data


@pytest.mark.asyncio
async def test_quota_row_persisted_in_db(client: AsyncClient, quota_auth_headers: dict):
    """After hitting /quota/me the UserQuota row should exist in the DB."""
    await client.get("/api/v1/quota/me", headers=quota_auth_headers)
    quota = await _get_quota_for_email("quota_user@example.com")
    assert quota is not None
    assert quota.tokens_used == 0
    assert quota.monthly_token_limit == 500_000


@pytest.mark.asyncio
async def test_quota_exceeded_returns_429(client: AsyncClient, quota_auth_headers: dict):
    """When tokens_used >= monthly_limit the quota check should return 429."""
    # Ensure the quota row exists first
    await client.get("/api/v1/quota/me", headers=quota_auth_headers)

    # Directly exhaust the quota in the DB
    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        quota_result = await session.execute(
            select(UserQuota).where(UserQuota.user_id == user.id)
        )
        quota = quota_result.scalar_one()
        quota.tokens_used = quota.monthly_token_limit
        await session.commit()

    # The next quota check should reject with 429
    from app.services.quota_service import QuotaService
    from app.utils.error_handlers import QuotaExceededError

    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        qs = QuotaService(session)
        with pytest.raises(QuotaExceededError) as exc_info:
            await qs.check_quota(user.id)

    assert exc_info.value.monthly_limit == 500_000
    assert exc_info.value.tokens_used == 500_000


@pytest.mark.asyncio
async def test_lazy_period_reset(client: AsyncClient, quota_auth_headers: dict):
    """If period_end is in the past, check_quota should reset and allow the request."""
    await client.get("/api/v1/quota/me", headers=quota_auth_headers)

    # Set period_end to the past and exhaust tokens
    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        quota_result = await session.execute(
            select(UserQuota).where(UserQuota.user_id == user.id)
        )
        quota = quota_result.scalar_one()
        quota.tokens_used = quota.monthly_token_limit
        quota.period_end = datetime.now(timezone.utc) - timedelta(days=1)
        await session.commit()

    from app.services.quota_service import QuotaService

    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        qs = QuotaService(session)
        # Should NOT raise — expired period triggers a reset
        await qs.check_quota(user.id)

    # Confirm reset happened in DB
    quota = await _get_quota_for_email("quota_user@example.com")
    assert quota is not None
    assert quota.tokens_used == 0
    assert quota.period_end > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_deduct_tokens_updates_db(client: AsyncClient, quota_auth_headers: dict):
    """deduct_tokens should increment tokens_used in the DB."""
    await client.get("/api/v1/quota/me", headers=quota_auth_headers)

    from app.services.quota_service import QuotaService

    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        qs = QuotaService(session)
        await qs.deduct_tokens(user.id, 1_000)

    quota = await _get_quota_for_email("quota_user@example.com")
    assert quota is not None
    assert quota.tokens_used == 1_000


@pytest.mark.asyncio
async def test_get_quota_info_reflects_usage(client: AsyncClient, quota_auth_headers: dict):
    """get_quota_info should return accurate remaining after deduction."""
    await client.get("/api/v1/quota/me", headers=quota_auth_headers)

    from app.services.quota_service import QuotaService

    async with TestSessionLocal() as session:
        user_result = await session.execute(
            select(User).where(User.email == "quota_user@example.com")
        )
        user = user_result.scalar_one()
        qs = QuotaService(session)
        await qs.deduct_tokens(user.id, 50_000)
        info = await qs.get_quota_info(user.id)

    assert info.tokens_used == 50_000
    assert info.remaining == 450_000
    assert info.monthly_limit == 500_000
    assert info.percentage_used == 10.0
