from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.avatar import AvatarConfirmRequest, AvatarUploadRequest, AvatarUploadResponse
from app.schemas.user import DietaryPreferences, UpdateProfileRequest, UserProfileResponse
from app.services import avatar_service, profile_service

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


@router.post("/me/avatar-upload-url", response_model=AvatarUploadResponse)
def create_avatar_upload_url(
    payload: AvatarUploadRequest, user: CurrentUser
) -> AvatarUploadResponse:
    return avatar_service.create_avatar_upload(user, payload)


@router.put("/me/avatar", response_model=UserProfileResponse)
def set_user_avatar(
    payload: AvatarConfirmRequest, user: CurrentUser, db: DbSession
) -> UserProfileResponse:
    return avatar_service.confirm_avatar(db, user, payload)
