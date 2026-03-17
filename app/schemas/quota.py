"""Pydantic schemas for quota endpoints."""

from datetime import datetime
from pydantic import BaseModel


class QuotaInfoResponse(BaseModel):
    monthly_limit: int
    tokens_used: int
    remaining: int
    period_end: datetime
    percentage_used: float
