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
        description="Natural language question about the dataset"
    )


class VisualizationResponse(BaseModel):
    """Schema for visualization data."""
    
    type: str = Field(..., description="Chart type (bar, line, scatter, pie, etc.)")
    title: str = Field(..., description="Visualization title")
    data: Dict[str, Any] = Field(..., description="Plotly chart data")
    layout: Optional[Dict[str, Any]] = Field(None, description="Plotly layout configuration")


class InsightResponse(BaseModel):
    """Schema for insights."""
    
    summary: str = Field(..., description="High-level summary of findings")
    key_findings: List[str] = Field(..., description="List of key findings")
    recommendations: Optional[List[str]] = Field(None, description="Actionable recommendations")


class QueryResponse(BaseModel):
    """Response schema for query results."""
    
    query_id: UUID = Field(..., description="Unique query identifier")
    dataset_id: UUID = Field(..., description="Dataset identifier")
    question: str = Field(..., description="Original question")
    answer: Optional[str] = Field(None, description="Natural language answer")
    
    visualizations: List[VisualizationResponse] = Field(
        default_factory=list,
        description="Generated visualizations"
    )
    insights: Optional[InsightResponse] = Field(None, description="Generated insights")
    statistics: Optional[Dict[str, Any]] = Field(None, description="Statistical results")
    
    execution_time: Optional[float] = Field(None, description="Query execution time in seconds")
    cache_hit: bool = Field(..., description="Whether result was from cache")
    status: str = Field(..., description="Query status")
    created_at: datetime = Field(..., description="Query timestamp")
    
    class Config:
        from_attributes = True


class QueryHistoryItem(BaseModel):
    """Schema for query in history list."""
    
    query_id: UUID
    question: str
    answer: Optional[str]
    status: str
    execution_time: Optional[float]
    created_at: datetime
    
    class Config:
        from_attributes = True


class QueryHistoryResponse(BaseModel):
    """Response schema for query history."""
    
    queries: List[QueryHistoryItem]
    total: int
