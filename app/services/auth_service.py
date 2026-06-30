import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.models.user import User
from app.services.referral_service import (
    bind_inviter,
    ensure_referral_code,
    reward_inviter_on_register,
)


async def get_or_create_user_by_openid(
    openid: str, db: AsyncSession, invite_code: str | None = None
) -> User:
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    is_new = False
    if user is None:
        user = User(openid=openid)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True

    if is_new and invite_code:
        await bind_inviter(db=db, user=user, invite_code=invite_code)
        await reward_inviter_on_register(db=db, user=user)

    # 确保每个用户都有邀请码
    await ensure_referral_code(db=db, user=user)
    return user


async def wechat_login(
    code: str, db: AsyncSession, invite_code: str | None = None
) -> User:
    """微信小程序 code 登录。"""
    if not settings.wechat_appid or not settings.wechat_secret:
        if not settings.wechat_dev_fallback:
            raise BadRequestException("微信登录尚未配置")
        # 仅在显式开启开发回退时，用 code 模拟 openid
        openid = f"dev-{code}"
        return await get_or_create_user_by_openid(openid, db, invite_code=invite_code)

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://api.weixin.qq.com/sns/jscode2session",
            params={
                "appid": settings.wechat_appid,
                "secret": settings.wechat_secret,
                "js_code": code,
                "grant_type": "authorization_code",
            },
        )
        data = resp.json()
    openid = data.get("openid")
    if not openid:
        raise BadRequestException("微信登录失败，请稍后重试")

    return await get_or_create_user_by_openid(openid, db, invite_code=invite_code)
