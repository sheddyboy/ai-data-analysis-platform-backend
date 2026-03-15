"""Pydantic schemas for query-related requests and responses."""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import UUID


class QueryRequest(BaseModel):
    """Request schema for querying a dataset."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural language question about the dataset",
    )
    session_id: Optional[UUID] = Field(
        default=None,
        description="Optional session ID to group related queries for conversation context",
    )
    parent_query_id: Optional[UUID] = Field(
        default=None,
        description="ID of a previous query in this session to provide conversation context",
    )


class VisualizationResponse(BaseModel):
    """Schema for visualization data."""

    type: str = Field(..., description="Chart type (bar, line, scatter, pie, etc.)")
    title: str = Field(..., description="Visualization title")
    data: List[Dict[str, Any]] = Field(..., description="Plotly chart data")
    layout: Optional[Dict[str, Any]] = Field(None, description="Plotly layout configuration")


class InsightResponse(BaseModel):
    """Schema for legacy insights (kept for cache compatibility)."""

    summary: str = Field(..., description="High-level summary of findings")
    key_findings: List[str] = Field(..., description="List of key findings")
    recommendations: Optional[List[str]] = Field(None, description="Actionable recommendations")


class FollowUpQuestionResponse(BaseModel):
    """A single suggested follow-up question."""

    question: str = Field(..., description="The follow-up question text")
    rationale: str = Field(..., description="Why this question is a useful next step")


class QueryResponse(BaseModel):
    """Response schema for query results."""

    query_id: UUID = Field(..., description="Unique query identifier")
    dataset_id: UUID = Field(..., description="Dataset identifier")
    question: str = Field(..., description="Original question")
    answer: Optional[str] = Field(None, description="Natural language answer")

    # Structured v2 output
    key_findings: List[str] = Field(default_factory=list, description="Key findings from the analysis")
    data_quality_notes: List[str] = Field(default_factory=list, description="Data quality observations")
    confidence: Optional[str] = Field(None, description="Answer confidence: high, medium, or low")
    analysis_plan: Optional[Dict[str, Any]] = Field(None, description="The step-by-step plan used by the agent")
    follow_up_questions: List[FollowUpQuestionResponse] = Field(
        default_factory=list, description="Suggested follow-up questions"
    )

    # Visualizations and legacy insights
    visualizations: List[VisualizationResponse] = Field(
        default_factory=list, description="Generated visualizations"
    )
    insights: Optional[InsightResponse] = Field(None, description="Legacy insights (from cache)")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Statistical results")

    # Execution metadata
    execution_time: Optional[float] = Field(None, description="Query execution time in seconds")
    cache_hit: bool = Field(..., description="Whether result was from cache")
    status: str = Field(..., description="Query status")
    created_at: datetime = Field(..., description="Query timestamp")

    # Conversation threading
    session_id: Optional[UUID] = Field(None, description="Session this query belongs to")
    parent_query_id: Optional[UUID] = Field(None, description="Parent query ID if this is a follow-up")

    class Config:
        from_attributes = True


class QueryHistoryItem(BaseModel):
    """Schema for query in history list."""

    query_id: UUID
    question: str
    answer: Optional[str]
    status: str
    confidence: Optional[str]
    execution_time: Optional[float]
    created_at: datetime
    session_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class QueryHistoryResponse(BaseModel):
    """Response schema for query history."""

    queries: List[QueryHistoryItem]
    total: int
