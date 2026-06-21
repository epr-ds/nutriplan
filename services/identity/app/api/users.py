from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.schemas.user import UserProfileResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfileResponse)
def get_current_user_profile(user: CurrentUser) -> UserProfileResponse:
    return UserProfileResponse.model_validate(user)
