"""File handling utilities."""

import uuid
from pathlib import Path
from fastapi import UploadFile
from typing import Tuple

from app.config import settings
from app.utils.error_handlers import FileProcessingError


ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def get_file_extension(filename: str) -> str:
    """Extract file extension from filename."""
    return Path(filename).suffix.lower()


def validate_file_type(filename: str) -> bool:
    """Validate if file type is supported."""
    return get_file_extension(filename) in ALLOWED_EXTENSIONS


async def save_upload_file(upload_file: UploadFile) -> Tuple[str, str, int]:
    """
    Save an uploaded file to local disk (DEBUG=True) or Cloudflare R2.

    Returns:
        Tuple of (file_path_or_r2_key, unique_filename, file_size)
        In debug mode: absolute local path (e.g. "/app/uploads/uuid.csv")
        In production: R2 object key (e.g. "datasets/uuid.csv")

    Raises:
        FileProcessingError: If validation or upload fails
    """
    if not upload_file.filename:
        raise FileProcessingError("No filename provided.")
    if not validate_file_type(upload_file.filename):
        raise FileProcessingError(
            f"Unsupported file type. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    extension = get_file_extension(upload_file.filename)
    unique_filename = f"{uuid.uuid4()}{extension}"

    try:
        content = await upload_file.read()
        file_size = len(content)

        if file_size > settings.MAX_UPLOAD_SIZE:
            raise FileProcessingError(
                f"File size exceeds maximum allowed size of "
                f"{settings.MAX_UPLOAD_SIZE / (1024 * 1024):.0f}MB"
            )

        if settings.USE_LOCAL_STORAGE:
            upload_dir = Path(settings.UPLOAD_DIR)
            upload_dir.mkdir(parents=True, exist_ok=True)
            local_path = upload_dir / unique_filename
            local_path.write_bytes(content)
            return str(local_path.resolve()), unique_filename, file_size
        else:
            r2_key = f"datasets/{unique_filename}"
            from app.services.storage_service import storage_service
            storage_service.upload(r2_key, content)
            return r2_key, unique_filename, file_size

    except FileProcessingError:
        raise
    except Exception as e:
        raise FileProcessingError(f"Failed to upload file: {str(e)}")
    finally:
        await upload_file.close()


def delete_file(file_path_or_key: str) -> None:
    """
    Delete a file from R2 (or local disk for legacy absolute paths).

    Args:
        file_path_or_key: R2 object key (e.g. "datasets/uuid.csv") or
                          legacy absolute path starting with "/"
    """
    try:
        if file_path_or_key.startswith("/"):
            # Legacy local path — remove from disk if it still exists
            path = Path(file_path_or_key)
            if path.exists():
                path.unlink()
        else:
            from app.services.storage_service import storage_service
            storage_service.delete(file_path_or_key)
    except Exception:
        pass  # Deletion failure is not critical
