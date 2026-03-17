"""API endpoints for dataset management."""

from fastapi import APIRouter, Depends, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from uuid import UUID

from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.dataset_service import DatasetService
from app.schemas.dataset import (
    DatasetUploadResponse,
    DatasetMetadataResponse,
    DatasetListResponse,
    DatasetListItem,
    DatasetMetadata,
)

router = APIRouter()


@router.post(
    "/upload",
    response_model=DatasetUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new dataset",
    description="Upload a CSV or Excel file for analysis"
)
async def upload_dataset(
    file: UploadFile = File(..., description="CSV or Excel file"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a new dataset for analysis.

    - **file**: CSV or Excel file (max 100MB)

    Returns the dataset ID and metadata.
    """
    service = DatasetService(db)
    dataset = await service.upload_dataset(file, user_id=current_user.id)
    
    # Build response
    metadata = DatasetMetadata(
        rows=dataset.row_count,
        columns=dataset.column_count,
        column_names=dataset.columns,
        column_types=dataset.column_types,
        summary_statistics=dataset.summary_statistics,
        sample_data=dataset.sample_data,
    )
    
    return DatasetUploadResponse(
        dataset_id=dataset.id,
        filename=dataset.original_filename,
        status=dataset.status,
        metadata=metadata,
        created_at=dataset.created_at,
    )


@router.get(
    "/{dataset_id}/metadata",
    response_model=DatasetMetadataResponse,
    summary="Get dataset metadata",
    description="Retrieve detailed metadata for a dataset"
)
async def get_dataset_metadata(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detailed metadata for a dataset.

    - **dataset_id**: UUID of the dataset

    Returns comprehensive dataset information including statistics and sample data.
    """
    service = DatasetService(db)
    dataset = await service.get_dataset(dataset_id, user_id=current_user.id)
    
    metadata = DatasetMetadata(
        rows=dataset.row_count,
        columns=dataset.column_count,
        column_names=dataset.columns,
        column_types=dataset.column_types,
        summary_statistics=dataset.summary_statistics,
        sample_data=dataset.sample_data,
    )
    
    return DatasetMetadataResponse(
        dataset_id=dataset.id,
        filename=dataset.original_filename,
        file_type=dataset.file_type,
        file_size=dataset.file_size,
        metadata=metadata,
        status=dataset.status,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


@router.get(
    "",
    response_model=DatasetListResponse,
    summary="List all datasets",
    description="Get a paginated list of all uploaded datasets"
)
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List the authenticated user's datasets with pagination.

    - **skip**: Number of records to skip (default: 0)
    - **limit**: Maximum number of records to return (default: 100)

    Returns a list of datasets with basic information.
    """
    service = DatasetService(db)
    datasets, total = await service.list_datasets(skip=skip, limit=limit, user_id=current_user.id)
    
    items = [
        DatasetListItem(
            dataset_id=d.id,
            filename=d.original_filename,
            file_type=d.file_type,
            row_count=d.row_count,
            column_count=d.column_count,
            status=d.status,
            created_at=d.created_at,
        )
        for d in datasets
    ]
    
    return DatasetListResponse(
        datasets=items,
        total=total
    )


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dataset",
    description="Delete a dataset and all associated queries"
)
async def delete_dataset(
    dataset_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete a dataset and all associated data.

    - **dataset_id**: UUID of the dataset to delete

    This will permanently delete the dataset file and all associated queries.
    """
    service = DatasetService(db)
    # Ownership check inside get_dataset
    await service.get_dataset(dataset_id, user_id=current_user.id)
    await service.delete_dataset(dataset_id)
    
    return None
