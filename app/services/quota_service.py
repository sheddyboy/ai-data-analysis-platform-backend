"""QuotaService — v5 monthly token quota with Redis fast-path."""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.config import settings
from app.models.user_quota import UserQuota
from app.services.cache_service import cache_service
from app.utils.error_handlers import QuotaExceededError


@dataclass
class QuotaInfo:
    monthly_limit: int
    tokens_used: int
    remaining: int
    period_end: datetime
    percentage_used: float


class QuotaService:
    """Per-request service for checking and deducting token quotas."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    # Redis key helpers                                                    #
    # ------------------------------------------------------------------ #

    def _remaining_key(self, user_id: UUID) -> str:
        return f"quota:{user_id}:remaining"

    def _limit_key(self, user_id: UUID) -> str:
        return f"quota:{user_id}:limit"

    def _period_end_key(self, user_id: UUID) -> str:
        return f"quota:{user_id}:period_end"

    # ------------------------------------------------------------------ #
    # DB helpers                                                           #
    # ------------------------------------------------------------------ #

    async def get_or_create_quota(self, user_id: UUID) -> UserQuota:
        """Return the quota row for this user, creating it lazily if absent."""
        result = await self.db.execute(
            select(UserQuota).where(UserQuota.user_id == user_id)
        )
        quota = result.scalar_one_or_none()
        if quota is None:
            now = datetime.now(timezone.utc)
            quota = UserQuota(
                user_id=user_id,
                monthly_token_limit=settings.FREE_TIER_MONTHLY_TOKEN_LIMIT,
                tokens_used=0,
                period_start=now,
                period_end=now + timedelta(days=30),
            )
            self.db.add(quota)
            await self.db.commit()
            await self.db.refresh(quota)
            logger.info("[quota] created new quota row for user {}", user_id)
        return quota

    # ------------------------------------------------------------------ #
    # Redis seeding                                                        #
    # ------------------------------------------------------------------ #

    async def _seed_redis(self, user_id: UUID, quota: UserQuota) -> None:
        """Populate Redis keys for this user's quota period."""
        if cache_service.redis is None:
            return
        try:
            remaining = max(0, quota.monthly_token_limit - quota.tokens_used)
            expire_at = int(quota.period_end.timestamp())

            await cache_service.redis.set(self._remaining_key(user_id), remaining)
            await cache_service.redis.expireat(self._remaining_key(user_id), expire_at)

            await cache_service.redis.set(self._limit_key(user_id), quota.monthly_token_limit)
            await cache_service.redis.expireat(self._limit_key(user_id), expire_at)

            await cache_service.redis.set(
                self._period_end_key(user_id), quota.period_end.isoformat()
            )
            await cache_service.redis.expireat(self._period_end_key(user_id), expire_at)

            logger.debug("[quota] seeded Redis for user {} (remaining={})", user_id, remaining)
        except Exception as e:
            logger.warning("[quota] Redis seed failed for user {}: {}", user_id, e)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    async def check_quota(self, user_id: UUID) -> None:
        """
        Fast-path quota check. Raises QuotaExceededError if the user has no
        remaining tokens. Falls back to DB if Redis is unavailable.
        """
        now = datetime.now(timezone.utc)

        # --- Redis fast path ---
        if cache_service.redis is not None:
            try:
                period_end_str = await cache_service.redis.get(self._period_end_key(user_id))

                if period_end_str is None:
                    # Keys missing — load from DB and seed
                    quota = await self.get_or_create_quota(user_id)
                    await self._seed_redis(user_id, quota)
                else:
                    period_end = datetime.fromisoformat(
                        period_end_str if isinstance(period_end_str, str)
                        else period_end_str.decode()
                    )
                    if period_end < now:
                        # Period expired — reset
                        quota = await self.get_or_create_quota(user_id)
                        await self._reset_period(user_id, quota)
                    else:
                        # Period current — read remaining from Redis
                        remaining_raw = await cache_service.redis.get(
                            self._remaining_key(user_id)
                        )
                        if remaining_raw is None:
                            # Evicted mid-period — re-seed from DB
                            quota = await self.get_or_create_quota(user_id)
                            await self._seed_redis(user_id, quota)
                            remaining_raw = await cache_service.redis.get(
                                self._remaining_key(user_id)
                            )

                        remaining = int(
                            remaining_raw if isinstance(remaining_raw, (int, str))
                            else remaining_raw.decode()
                        )
                        if remaining <= 0:
                            quota = await self.get_or_create_quota(user_id)
                            raise QuotaExceededError(
                                tokens_used=quota.tokens_used,
                                monthly_limit=quota.monthly_token_limit,
                                resets_at=quota.period_end.isoformat(),
                            )
                        return  # quota OK

            except QuotaExceededError:
                raise
            except Exception as e:
                logger.warning("[quota] Redis check failed, falling back to DB: {}", e)

        # --- DB fallback ---
        quota = await self.get_or_create_quota(user_id)
        if quota.period_end < now:
            await self._reset_period(user_id, quota)
        elif quota.tokens_used >= quota.monthly_token_limit:
            raise QuotaExceededError(
                tokens_used=quota.tokens_used,
                monthly_limit=quota.monthly_token_limit,
                resets_at=quota.period_end.isoformat(),
            )

    async def deduct_tokens(self, user_id: UUID, tokens: int) -> None:
        """Deduct actual tokens from both Redis and PostgreSQL."""
        if tokens <= 0:
            return

        # Redis deduction (atomic)
        if cache_service.redis is not None:
            try:
                new_remaining = await cache_service.redis.decrby(
                    self._remaining_key(user_id), tokens
                )
                logger.debug(
                    "[quota] deducted {} tokens for user {}, redis_remaining={}",
                    tokens, user_id, new_remaining,
                )
            except Exception as e:
                logger.warning("[quota] Redis decrby failed for user {}: {}", user_id, e)

        # PostgreSQL update (no SELECT needed)
        now = datetime.now(timezone.utc)
        await self.db.execute(
            update(UserQuota)
            .where(UserQuota.user_id == user_id)
            .values(
                tokens_used=UserQuota.tokens_used + tokens,
                updated_at=now,
            )
        )
        await self.db.commit()
        logger.info("[quota] deducted {} tokens for user {} in DB", tokens, user_id)

    async def get_quota_info(self, user_id: UUID) -> QuotaInfo:
        """Return current quota status for a user."""
        quota = await self.get_or_create_quota(user_id)
        now = datetime.now(timezone.utc)
        if quota.period_end < now:
            await self._reset_period(user_id, quota)

        remaining = max(0, quota.monthly_token_limit - quota.tokens_used)
        percentage = (
            round(quota.tokens_used / quota.monthly_token_limit * 100, 2)
            if quota.monthly_token_limit
            else 0.0
        )
        return QuotaInfo(
            monthly_limit=quota.monthly_token_limit,
            tokens_used=quota.tokens_used,
            remaining=remaining,
            period_end=quota.period_end,
            percentage_used=percentage,
        )

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    async def _reset_period(self, user_id: UUID, quota: UserQuota) -> None:
        """Reset quota to a fresh 30-day period."""
        now = datetime.now(timezone.utc)
        quota.tokens_used = 0
        quota.period_start = now
        quota.period_end = now + timedelta(days=30)
        quota.updated_at = now
        await self.db.commit()
        await self.db.refresh(quota)
        await self._seed_redis(user_id, quota)
        logger.info("[quota] reset period for user {}", user_id)
