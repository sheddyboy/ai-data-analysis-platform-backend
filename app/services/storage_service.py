"""Cloudflare R2 storage service (S3-compatible)."""

import io
import boto3
from botocore.exceptions import ClientError

from app.config import settings


class StorageService:
    """Thin wrapper around boto3 S3 client pointed at Cloudflare R2."""

    def __init__(self) -> None:
        self._client = None
        self._bucket = settings.R2_BUCKET_NAME

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"https://{settings.R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
                aws_access_key_id=settings.R2_ACCESS_KEY_ID,
                aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
                region_name="auto",
            )
        return self._client

    def upload(self, key: str, data: bytes) -> None:
        """Upload bytes to R2 under the given key."""
        self._get_client().put_object(Bucket=self._bucket, Key=key, Body=data)

    def download(self, key: str) -> io.BytesIO:
        """Download an object from R2 and return it as a BytesIO buffer."""
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        return io.BytesIO(response["Body"].read())

    def delete(self, key: str) -> None:
        """Delete an object from R2. Silently ignores errors."""
        try:
            self._get_client().delete_object(Bucket=self._bucket, Key=key)
        except ClientError:
            pass


storage_service = StorageService()
