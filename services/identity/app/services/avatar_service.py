"""Avatar upload use-cases (IDN-304): presigned upload + confirm with ownership check."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import storage
from app.core.config import settings
from app.db.models import User
from app.schemas.avatar import AvatarConfirmRequest, AvatarUploadRequest, AvatarUploadResponse
from app.schemas.user import UserProfileResponse


def create_avatar_upload(user: User, payload: AvatarUploadRequest) -> AvatarUploadResponse:
    key = storage.build_avatar_key(user.id, payload.content_type)
    upload_url = storage.create_presigned_put(key, payload.content_type)
    return AvatarUploadResponse(
        upload_url=upload_url,
        key=key,
        expires_in=settings.avatar_upload_ttl_seconds,
        required_headers={"Content-Type": payload.content_type},
    )


def confirm_avatar(db: Session, user: User, payload: AvatarConfirmRequest) -> UserProfileResponse:
    if not storage.key_belongs_to_user(user.id, payload.key):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Object key does not belong to this user")
    user.avatar_url = storage.public_url(payload.key)
    db.commit()
    db.refresh(user)
    return UserProfileResponse.model_validate(user)
