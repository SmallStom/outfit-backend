from fastapi import APIRouter
from sqlalchemy import select

from app.core.exceptions import NotFoundException
from app.core.responses import success
from app.core.security import create_access_token
from app.db.dependencies import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserProfile,
    UserProfileUpdate,
    WechatLoginRequest,
)
from app.services.auth_service import wechat_login

auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/user", tags=["user"])


@auth_router.post("/login")
async def login(body: WechatLoginRequest, db: DbSession):
    user = await wechat_login(body.code, db)
    access_token = create_access_token(user.id)
    return success(
        data=TokenResponse(access_token=access_token, token_type="bearer").model_dump()
    )


@auth_router.post("/refresh")
async def refresh(user_id: CurrentUserId):
    access_token = create_access_token(user_id)
    return success(
        data=TokenResponse(access_token=access_token, token_type="bearer").model_dump()
    )


@user_router.get("/profile")
async def get_profile(db: DbSession, user_id: CurrentUserId):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    return success(data=UserProfile.model_validate(user).model_dump())


@user_router.put("/profile")
async def update_profile(
    body: UserProfileUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    if body.nickname is not None:
        user.nickname = body.nickname
    if body.avatar_url is not None:
        user.avatar_url = body.avatar_url
    if body.gender is not None:
        user.gender = body.gender
    await db.commit()
    await db.refresh(user)
    return success(data=UserProfile.model_validate(user).model_dump())
