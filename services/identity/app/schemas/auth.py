from pydantic import EmailStr, Field

from app.schemas.base import CamelModel
from app.schemas.user import UserProfileResponse


class RegisterRequest(CamelModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=2)


class LoginRequest(CamelModel):
    email: EmailStr
    password: str


class RefreshRequest(CamelModel):
    refresh_token: str


class AuthResponse(CamelModel):
    access_token: str
    refresh_token: str
    expires_in: int
    user: UserProfileResponse
