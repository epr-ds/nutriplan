import uuid
from datetime import datetime

from pydantic import EmailStr

from app.schemas.base import CamelModel


class UserProfileResponse(CamelModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    avatar_url: str | None = None
    dietary_preferences: dict | None = None
    created_at: datetime
