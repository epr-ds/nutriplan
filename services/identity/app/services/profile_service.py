"""Profile and dietary-preference use-cases (IDN-301/302/303)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import User
from app.schemas.user import DietaryPreferences, UpdateProfileRequest, UserProfileResponse


def update_profile(db: Session, user: User, payload: UpdateProfileRequest) -> UserProfileResponse:
    """Apply a partial update to ``name``/``avatarUrl`` (unset fields are preserved)."""
    data = payload.model_dump(exclude_unset=True, mode="json")
    if data.get("name") is not None:
        user.name = data["name"]
    if "avatar_url" in data:
        user.avatar_url = data["avatar_url"]
    db.commit()
    db.refresh(user)
    return UserProfileResponse.model_validate(user)


def update_dietary_preferences(
    db: Session, user: User, payload: DietaryPreferences
) -> DietaryPreferences:
    """Merge the supplied preferences over the stored ones (partial update)."""
    incoming = payload.model_dump(by_alias=True, exclude_unset=True, mode="json")
    merged = dict(user.dietary_preferences or {})
    merged.update(incoming)
    user.dietary_preferences = merged
    db.commit()
    db.refresh(user)
    return DietaryPreferences.model_validate(merged)
