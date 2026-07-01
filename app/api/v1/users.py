from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.exceptions import NotFoundException
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.auth import UserProfile
from app.schemas.common import to_camel
from app.schemas.user import (
    UserListItem,
    UserStats,
)
from app.services.user_service import (
    get_user_stats,
    list_followers,
    list_following,
    toggle_follow,
)

router = APIRouter(prefix="/users", tags=["users"])


class CompleteOnboardingRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    skipped: bool = Field(default=False, description="用户是否跳过了引导步骤")


class CompleteOnboardingResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    user: dict
    skipped: bool


@router.post("/me/complete-onboarding")
async def complete_onboarding(
    body: CompleteOnboardingRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    user.is_new_user = False
    await db.commit()
    await db.refresh(user)
    return success(data={
        "user": UserProfile.model_validate(user).model_dump(by_alias=True),
        "skipped": body.skipped,
    })


@router.get("/me/stats")
async def get_my_stats(db: DbSession, user_id: CurrentUserId):
    data = await get_user_stats(db=db, user_id=UUID(user_id))
    return success(data=UserStats.model_validate(data).model_dump(by_alias=True))


@router.get("/{target_user_id}/stats")
async def get_user_stats_endpoint(
    target_user_id: UUID,
    db: DbSession,
):
    data = await get_user_stats(db=db, user_id=target_user_id)
    return success(data=UserStats.model_validate(data).model_dump(by_alias=True))


@router.post("/{target_user_id}/follow")
async def follow_user(
    target_user_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    result = await toggle_follow(
        db=db, current_user_id=UUID(user_id), target_user_id=target_user_id
    )
    return success(data=result)


@router.get("/{target_user_id}/followers")
async def get_followers(
    target_user_id: UUID,
    db: DbSession,
):
    data = await list_followers(db=db, user_id=target_user_id)
    return success(
        data=[
            UserListItem.model_validate(row).model_dump(by_alias=True) for row in data
        ]
    )


@router.get("/{target_user_id}/following")
async def get_following(
    target_user_id: UUID,
    db: DbSession,
):
    data = await list_following(db=db, user_id=target_user_id)
    return success(
        data=[
            UserListItem.model_validate(row).model_dump(by_alias=True) for row in data
        ]
    )
