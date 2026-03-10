"""Service for dataset management operations."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import UploadFile
from typing import List, Optional
from uuid import UUID

from app.models.dataset import Dataset
from app.services.metadata_extractor import MetadataExtractor
from app.utils.file_utils import save_upload_file, get_file_extension
from app.utils.error_handlers import DatasetNotFoundError, FileProcessingError


class DatasetService:
    """Service for managing dataset operations."""
    
    def __init__(self, db: AsyncSession):
        """
        Initialize dataset service.
        
        Args:
            db: Database session
        """
        self.db = db
        self.metadata_extractor = MetadataExtractor()
    
    async def upload_dataset(self, upload_file: UploadFile) -> Dataset:
        """
        Upload and process a new dataset.
        
        Args:
            upload_file: Uploaded file
            
        Returns:
            Created Dataset model
            
        Raises:
            FileProcessingError: If file processing fails
        """
        # Save file to disk
        file_path, unique_filename, file_size = await save_upload_file(upload_file)
        
        try:
            # Extract metadata
            df, metadata = await self.metadata_extractor.extract_metadata(file_path)
            
            # Create dataset record
            dataset = Dataset(
                filename=unique_filename,
                original_filename=upload_file.filename,
                file_path=file_path,
                file_size=file_size,
                file_type=get_file_extension(upload_file.filename).lstrip('.'),
                row_count=metadata['rows'],
                column_count=metadata['columns'],
                columns=metadata['column_names'],
                column_types=metadata['column_types'],
                summary_statistics=metadata['summary_statistics'],
                sample_data=metadata['sample_data'],
                status="ready"
            )
            
            self.db.add(dataset)
            await self.db.commit()
            await self.db.refresh(dataset)
            
            return dataset
            
        except Exception as e:
            await self.db.rollback()
            raise FileProcessingError(f"Failed to process dataset: {str(e)}")
    
    async def get_dataset(self, dataset_id: UUID) -> Dataset:
        """
        Get a dataset by ID.
        
        Args:
            dataset_id: Dataset UUID
            
        Returns:
            Dataset model
            
        Raises:
            DatasetNotFoundError: If dataset not found
        """
        result = await self.db.execute(
            select(Dataset).where(Dataset.id == dataset_id)
        )
        dataset = result.scalar_one_or_none()
        
        if not dataset:
            raise DatasetNotFoundError(str(dataset_id))
        
        return dataset
    
    async def get_dataset_metadata(self, dataset_id: UUID) -> Dataset:
        """
        Get dataset metadata.
        
        Args:
            dataset_id: Dataset UUID
            
        Returns:
            Dataset model with metadata
            
        Raises:
            DatasetNotFoundError: If dataset not found
        """
        return await self.get_dataset(dataset_id)
    
    async def list_datasets(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> tuple[List[Dataset], int]:
        """
        List all datasets with pagination.
        
        Args:
            skip: Number of records to skip
            limit: Maximum number of records to return
            
        Returns:
            Tuple of (datasets list, total count)
        """
        # Get total count
        count_result = await self.db.execute(select(func.count(Dataset.id)))
        total = count_result.scalar_one()
        
        # Get datasets
        result = await self.db.execute(
            select(Dataset)
            .order_by(Dataset.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        datasets = result.scalars().all()
        
        return list(datasets), total
    
    async def delete_dataset(self, dataset_id: UUID) -> bool:
        """
        Delete a dataset.
        
        Args:
            dataset_id: Dataset UUID
            
        Returns:
            True if deleted successfully
            
        Raises:
            DatasetNotFoundError: If dataset not found
        """
        dataset = await self.get_dataset(dataset_id)
        
        # Delete file from disk
        from app.utils.file_utils import delete_file
        delete_file(dataset.file_path)
        
        # Delete from database
        await self.db.delete(dataset)
        await self.db.commit()
        
        return True
