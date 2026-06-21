import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import EmailStr, Field, HttpUrl, field_validator

from app.schemas.base import CamelModel

DietType = Literal["omnivore", "vegetarian", "vegan", "keto", "paleo", "mediterranean"]
Cuisine = Literal["mexican", "italian", "asian", "mediterranean", "american", "indian"]


class MacroTargets(CamelModel):
    protein_grams: int | None = None
    carbs_grams: int | None = None
    fat_grams: int | None = None
    sugar_grams: int | None = None


class DietaryPreferences(CamelModel):
    diet_type: DietType | None = None
    allergies: list[str] | None = None
    daily_calorie_target: int | None = Field(default=None, ge=1200, le=5000)
    macro_targets: MacroTargets | None = None
    excluded_ingredients: list[str] | None = None
    cuisine_preferences: list[Cuisine] | None = None
    appetite_satisfaction_level: int | None = Field(default=None, ge=1, le=5)


class UpdateProfileRequest(CamelModel):
    name: str | None = Field(default=None, min_length=2)
    avatar_url: HttpUrl | None = None


class UserProfileResponse(CamelModel):
    id: uuid.UUID
    email: EmailStr
    name: str
    avatar_url: str | None = None
    dietary_preferences: DietaryPreferences | None = None
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _ensure_utc(cls, value: datetime) -> datetime:
        # SQLite drops tzinfo on read-back; emit an unambiguous RFC 3339 timestamp regardless.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
