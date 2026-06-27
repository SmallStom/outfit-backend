import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.models.user import User


async def get_or_create_user_by_openid(openid: str, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(openid=openid)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def wechat_login(code: str, db: AsyncSession) -> User:
    """微信小程序 code 登录；未配置微信密钥时进入开发模式，用 code 生成测试 openid。"""
    if settings.wechat_appid and settings.wechat_secret:
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
            raise BadRequestException(f"微信登录失败: {data.get('errmsg', '未知错误')}")
    else:
        # 开发模式：没有配置微信密钥时，用 code 模拟 openid
        openid = f"dev-{code}"

    return await get_or_create_user_by_openid(openid, db)
