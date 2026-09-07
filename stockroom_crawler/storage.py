"""Product image objects in MinIO.

The bucket stays private: the DB records only an object key, and the Go
service is the sole reader via GET /media/{key}.
"""

from __future__ import annotations

import io
import logging
from hashlib import sha256

from minio import Minio

from stockroom_crawler.config import Settings

log = logging.getLogger(__name__)

_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}


class ImageStore:
    def __init__(self, settings: Settings):
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            log.info("Created MinIO bucket %s", self.bucket)

    def put(self, product_id: str, body: bytes, content_type: str) -> str:
        """Store the image and return its object key.

        The key is content-addressed, so re-crawling overwrites in place
        instead of accumulating duplicates.
        """
        digest = sha256(body).hexdigest()[:32]
        key = f"products/{product_id}/{digest}{_EXTENSIONS.get(content_type, '.jpg')}"
        self.client.put_object(
            self.bucket,
            key,
            io.BytesIO(body),
            length=len(body),
            content_type=content_type,
        )
        return key
