"""Pydantic schemas for session-related requests and responses."""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from uuid import UUID

from app.schemas.query import QueryHistoryItem


class SessionCreateRequest(BaseModel):
    """Request schema for creating a chat session."""

    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional session title. Auto-set from the first question if omitted.",
    )


class SessionQueryRequest(BaseModel):
    """Request schema for sending a message within a session."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural language question about the dataset",
    )


class SessionResponse(BaseModel):
    """Response schema for a session."""

    session_id: UUID
    dataset_id: UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Response schema for listing sessions."""

    sessions: List[SessionResponse]
    total: int


class SessionMessagesResponse(BaseModel):
    """Response schema for a session with its full message history."""

    session_id: UUID
    dataset_id: UUID
    title: str
    messages: List[QueryHistoryItem]
    total: int
