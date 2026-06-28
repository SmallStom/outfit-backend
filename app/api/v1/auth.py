from fastapi import APIRouter
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ForbiddenException, NotFoundException
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
from app.schemas.user import (
    UserSettingsOut,
    UserSettingsUpdate,
)
from app.services.auth_service import get_or_create_user_by_openid, wechat_login
from app.services.user_service import (
    get_or_create_settings,
    update_settings,
)

auth_router = APIRouter(prefix="/auth", tags=["auth"])
user_router = APIRouter(prefix="/user", tags=["user"])


@auth_router.post("/login")
async def login(body: WechatLoginRequest, db: DbSession):
    user = await wechat_login(body.code, db)
    access_token = create_access_token(user.id)
    return success(
        data=TokenResponse(access_token=access_token, token_type="bearer").model_dump(by_alias=True)
    )


@auth_router.post("/dev-login")
async def dev_login(db: DbSession):
    if settings.app_env == "production":
        raise ForbiddenException("开发登录接口仅在非生产环境可用")
    user = await get_or_create_user_by_openid("dev-user", db)
    access_token = create_access_token(user.id)
    return success(
        data=TokenResponse(access_token=access_token, token_type="bearer").model_dump(by_alias=True)
    )


@auth_router.post("/refresh")
async def refresh(user_id: CurrentUserId):
    access_token = create_access_token(user_id)
    return success(
        data=TokenResponse(access_token=access_token, token_type="bearer").model_dump(by_alias=True)
    )


@user_router.get("/profile")
async def get_profile(db: DbSession, user_id: CurrentUserId):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    return success(data=UserProfile.model_validate(user).model_dump(by_alias=True))


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
    if body.avatar_color is not None:
        user.avatar_color = body.avatar_color
    if body.bio is not None:
        user.bio = body.bio
    if body.gender is not None:
        user.gender = body.gender
    await db.commit()
    await db.refresh(user)
    return success(data=UserProfile.model_validate(user).model_dump(by_alias=True))


@user_router.get("/settings")
async def get_settings(db: DbSession, user_id: CurrentUserId):
    user_settings = await get_or_create_settings(db=db, user_id=user_id)
    return success(
        data=UserSettingsOut.model_validate(user_settings).model_dump(by_alias=True)
    )


@user_router.put("/settings")
async def update_user_settings(
    body: UserSettingsUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    user_settings = await update_settings(
        db=db,
        user_id=user_id,
        notification_prefs=body.notification_prefs,
        privacy_prefs=body.privacy_prefs,
    )
    return success(
        data=UserSettingsOut.model_validate(user_settings).model_dump(by_alias=True)
    )
