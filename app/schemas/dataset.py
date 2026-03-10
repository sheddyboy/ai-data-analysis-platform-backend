"""Pydantic schemas for dataset-related requests and responses."""

from pydantic import BaseModel, Field
from typing import Dict, List, Any, Optional
from datetime import datetime
from uuid import UUID


class DatasetMetadata(BaseModel):
    """Dataset metadata schema."""
    
    rows: int = Field(..., description="Number of rows in dataset")
    columns: int = Field(..., description="Number of columns in dataset")
    column_names: List[str] = Field(..., description="List of column names")
    column_types: Dict[str, str] = Field(..., description="Column data types")
    summary_statistics: Optional[Dict[str, Any]] = Field(None, description="Summary statistics")
    sample_data: Optional[List[Dict[str, Any]]] = Field(None, description="Sample data rows")


class DatasetUploadResponse(BaseModel):
    """Response schema for dataset upload."""
    
    dataset_id: UUID = Field(..., description="Unique dataset identifier")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Dataset processing status")
    metadata: DatasetMetadata = Field(..., description="Dataset metadata")
    created_at: datetime = Field(..., description="Upload timestamp")
    
    class Config:
        from_attributes = True


class DatasetMetadataResponse(BaseModel):
    """Response schema for dataset metadata retrieval."""
    
    dataset_id: UUID
    filename: str
    file_type: str
    file_size: int
    metadata: DatasetMetadata
    status: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class DatasetListItem(BaseModel):
    """Schema for dataset in list response."""
    
    dataset_id: UUID
    filename: str
    file_type: str
    row_count: int
    column_count: int
    status: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class DatasetListResponse(BaseModel):
    """Response schema for listing datasets."""
    
    datasets: List[DatasetListItem]
    total: int
