"""File handling utilities."""

import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile
from typing import Tuple
from app.config import settings
from app.utils.error_handlers import FileProcessingError


ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def get_file_extension(filename: str) -> str:
    """
    Extract file extension from filename.
    
    Args:
        filename: Original filename
        
    Returns:
        File extension (lowercase, with dot)
    """
    return Path(filename).suffix.lower()


def validate_file_type(filename: str) -> bool:
    """
    Validate if file type is supported.
    
    Args:
        filename: Original filename
        
    Returns:
        True if file type is supported, False otherwise
    """
    extension = get_file_extension(filename)
    return extension in ALLOWED_EXTENSIONS


async def save_upload_file(upload_file: UploadFile) -> Tuple[str, str, int]:
    """
    Save uploaded file to disk.
    
    Args:
        upload_file: FastAPI UploadFile object
        
    Returns:
        Tuple of (file_path, unique_filename, file_size)
        
    Raises:
        FileProcessingError: If file processing fails
    """
    # Validate file type
    if not validate_file_type(upload_file.filename):
        raise FileProcessingError(
            f"Unsupported file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Create upload directory if it doesn't exist
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate unique filename
    extension = get_file_extension(upload_file.filename)
    unique_filename = f"{uuid.uuid4()}{extension}"
    file_path = upload_dir / unique_filename
    
    try:
        # Read file content
        content = await upload_file.read()
        file_size = len(content)
        
        # Check file size
        if file_size > settings.MAX_UPLOAD_SIZE:
            raise FileProcessingError(
                f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE / (1024*1024):.0f}MB"
            )
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)
        
        return str(file_path), unique_filename, file_size
        
    except Exception as e:
        # Clean up partial file if it exists
        if file_path.exists():
            file_path.unlink()
        raise FileProcessingError(f"Failed to save file: {str(e)}")
    finally:
        await upload_file.close()


def delete_file(file_path: str) -> None:
    """
    Delete a file from disk.
    
    Args:
        file_path: Path to file to delete
    """
    try:
        path = Path(file_path)
        if path.exists():
            path.unlink()
    except Exception:
        # Silently fail - file deletion is not critical
        pass
