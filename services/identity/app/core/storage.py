"""S3-compatible object storage for avatar uploads (IDN-304).

Presigned URLs are generated locally by botocore (no network round-trip), so the upload
target is computed without the storage backend being reachable. The actual bytes are
uploaded by the client straight to the bucket, keeping image data off the API path.
"""

from __future__ import annotations

import uuid
from functools import lru_cache

import boto3
from botocore.client import Config

from app.core.config import settings

_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


def allowed_content_types() -> tuple[str, ...]:
    return tuple(p.strip() for p in settings.avatar_allowed_content_types.split(",") if p.strip())


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        # Path-style addressing keeps URLs as <endpoint>/<bucket>/<key>, which MinIO needs.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def build_avatar_key(user_id: uuid.UUID, content_type: str) -> str:
    ext = _EXTENSIONS.get(content_type, "bin")
    return f"{user_id}/{uuid.uuid4().hex}.{ext}"


def key_belongs_to_user(user_id: uuid.UUID, key: str) -> bool:
    """Guard against a client confirming an object key it does not own."""
    return key.startswith(f"{user_id}/")


def create_presigned_put(key: str, content_type: str) -> str:
    return _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.avatar_bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.avatar_upload_ttl_seconds,
    )


def public_url(key: str) -> str:
    return f"{settings.s3_endpoint_url.rstrip('/')}/{settings.avatar_bucket}/{key}"
