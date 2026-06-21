from typing import Literal

from app.schemas.base import CamelModel

AvatarContentType = Literal["image/jpeg", "image/png", "image/webp"]


class AvatarUploadRequest(CamelModel):
    content_type: AvatarContentType


class AvatarUploadResponse(CamelModel):
    upload_url: str
    key: str
    expires_in: int
    required_headers: dict[str, str]


class AvatarConfirmRequest(CamelModel):
    key: str
