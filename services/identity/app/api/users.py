from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.user import DietaryPreferences, UpdateProfileRequest, UserProfileResponse
from app.services import profile_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(user: CurrentUser) -> UserProfileResponse:
    return UserProfileResponse.model_validate(user)


@router.put("/me", response_model=UserProfileResponse)
def update_current_user_profile(
    payload: UpdateProfileRequest, user: CurrentUser, db: DbSession
) -> UserProfileResponse:
    return profile_service.update_profile(db, user, payload)


@router.put("/me/dietary-preferences", response_model=DietaryPreferences)
def update_current_user_dietary_preferences(
    payload: DietaryPreferences, user: CurrentUser, db: DbSession
) -> DietaryPreferences:
    return profile_service.update_dietary_preferences(db, user, payload)
