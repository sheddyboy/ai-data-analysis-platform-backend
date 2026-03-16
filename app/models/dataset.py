"""Database models for datasets and queries."""

from sqlalchemy import String, Integer, DateTime, JSON, Text, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import uuid
from app.database import Base


class Dataset(Base):
    """Model for storing uploaded datasets and their metadata."""

    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    file_size: Mapped[int] = mapped_column(Integer)  # in bytes
    file_type: Mapped[str] = mapped_column(String(50))  # csv or excel

    # Metadata
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    columns: Mapped[List[str]] = mapped_column(JSON)  # List of column names
    column_types: Mapped[Dict[str, str]] = mapped_column(
        JSON
    )  # Dict of column -> dtype
    summary_statistics: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )  # Basic stats for numeric columns
    sample_data: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True
    )  # First 5 rows

    # Status
    status: Mapped[str] = mapped_column(
        String(50), default="ready"
    )  # ready, processing, error
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    queries: Mapped[list["Query"]] = relationship(
        "Query", back_populates="dataset", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["Session"]] = relationship(
        "Session", back_populates="dataset", cascade="all, delete-orphan"
    )  # type: ignore[name-defined]

    def __repr__(self):
        return f"<Dataset(id={self.id}, filename={self.filename})>"


class Query(Base):
    """Model for storing queries and their results."""

    __tablename__ = "queries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE")
    )

    # Query
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Results
    visualizations: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # List of visualization objects
    insights: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Insights object
    statistics: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Statistical results

    # Execution metadata
    execution_time: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )  # in seconds
    status: Mapped[str] = mapped_column(
        String(50), default="pending"
    )  # pending, completed, failed
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    agent_steps: Mapped[Optional[dict]] = mapped_column(
        JSON, nullable=True
    )  # Log of agent's reasoning steps

    # Cache
    cache_hit: Mapped[str] = mapped_column(
        String(10), default="false"
    )  # "true" or "false"

    # V2: structured output fields
    key_findings: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    data_quality_notes: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    confidence: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    analysis_plan: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    follow_up_questions: Mapped[Optional[List[Dict[str, str]]]] = mapped_column(
        JSON, nullable=True
    )

    # V3: conversation threading via Session
    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    parent_query_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("queries.id", ondelete="SET NULL"), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="queries")
    session: Mapped[Optional["Session"]] = relationship(
        "Session", back_populates="queries"
    )  # type: ignore[name-defined]
    parent_query: Mapped[Optional["Query"]] = relationship(
        "Query", remote_side="Query.id", foreign_keys="Query.parent_query_id"
    )

    def __repr__(self):
        return f"<Query(id={self.id}, question={self.question[:50]})>"
