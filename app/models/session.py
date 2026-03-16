"""Database model for chat sessions."""

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone
from typing import Optional
import uuid
from app.database import Base


class Session(Base):
    """A chat session grouping related queries against a single dataset."""

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"))

    title: Mapped[str] = mapped_column(String(255), default="New session")

    # Reserved for v4 auth — nullable until then
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="sessions")  # type: ignore[name-defined]
    queries: Mapped[list["Query"]] = relationship("Query", back_populates="session", cascade="all, delete-orphan")  # type: ignore[name-defined]

    def __repr__(self):
        return f"<Session(id={self.id}, title={self.title!r})>"
