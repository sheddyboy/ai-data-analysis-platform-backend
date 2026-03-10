"""Database models for datasets and queries."""

from sqlalchemy import Column, String, Integer, DateTime, JSON, Text, ForeignKey, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.database import Base


class Dataset(Base):
    """Model for storing uploaded datasets and their metadata."""
    
    __tablename__ = "datasets"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False)  # in bytes
    file_type = Column(String(50), nullable=False)  # csv or excel
    
    # Metadata
    row_count = Column(Integer, nullable=False)
    column_count = Column(Integer, nullable=False)
    columns = Column(JSON, nullable=False)  # List of column names
    column_types = Column(JSON, nullable=False)  # Dict of column -> dtype
    summary_statistics = Column(JSON, nullable=True)  # Basic stats for numeric columns
    sample_data = Column(JSON, nullable=True)  # First 5 rows
    
    # Status
    status = Column(String(50), default="ready")  # ready, processing, error
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    queries = relationship("Query", back_populates="dataset", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Dataset(id={self.id}, filename={self.filename})>"


class Query(Base):
    """Model for storing queries and their results."""
    
    __tablename__ = "queries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    
    # Query
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    
    # Results
    visualizations = Column(JSON, nullable=True)  # List of visualization objects
    insights = Column(JSON, nullable=True)  # Insights object
    statistics = Column(JSON, nullable=True)  # Statistical results
    
    # Execution metadata
    execution_time = Column(Float, nullable=True)  # in seconds
    status = Column(String(50), default="pending")  # pending, completed, failed
    error_message = Column(Text, nullable=True)
    agent_steps = Column(JSON, nullable=True)  # Log of agent's reasoning steps
    
    # Cache
    cache_hit = Column(String(10), default="false")  # "true" or "false"
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Relationships
    dataset = relationship("Dataset", back_populates="queries")
    
    def __repr__(self):
        return f"<Query(id={self.id}, question={self.question[:50]})>"
