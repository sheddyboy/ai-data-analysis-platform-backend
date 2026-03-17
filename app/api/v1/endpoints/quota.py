"""Quota endpoints — current user's monthly token quota."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.quota_service import QuotaService
from app.schemas.quota import QuotaInfoResponse

router = APIRouter()


@router.get(
    "/me",
    response_model=QuotaInfoResponse,
    summary="Get my token quota",
    description="Returns the current user's monthly token quota status.",
)
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    info = await QuotaService(db).get_quota_info(current_user.id)
    return QuotaInfoResponse(
        monthly_limit=info.monthly_limit,
        tokens_used=info.tokens_used,
        remaining=info.remaining,
        period_end=info.period_end,
        percentage_used=info.percentage_used,
    )
