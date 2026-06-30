import secrets
import string
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj
from app.models.user import User
from app.services.credit_service import earn_credits


def _generate_referral_code() -> str:
    """生成 8 位字母数字邀请码。"""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


async def ensure_referral_code(db: AsyncSession, user: User) -> str:
    """确保用户有邀请码，没有则生成并保存。"""
    if user.referral_code:
        return user.referral_code

    for _ in range(10):
        code = _generate_referral_code()
        existing = await db.execute(
            select(User).where(User.referral_code == code)
        )
        if existing.scalar_one_or_none() is None:
            user.referral_code = code
            await db.commit()
            return code

    raise BadRequestException("邀请码生成失败，请重试")


async def bind_inviter(db: AsyncSession, user: User, invite_code: str) -> None:
    """新用户注册时绑定邀请人。"""
    if not invite_code:
        return
    if user.invited_by:
        return

    result = await db.execute(
        select(User).where(User.referral_code.ilike(invite_code))
    )
    inviter = result.scalar_one_or_none()
    if inviter is None:
        raise BadRequestException("邀请码无效")
    if inviter.id == user.id:
        raise BadRequestException("不能邀请自己")

    user.invited_by = inviter.id
    await db.commit()


async def reward_inviter_on_register(db: AsyncSession, user: User) -> None:
    """被邀请人注册成功后给邀请人发积分奖励。"""
    if not user.invited_by:
        return

    reward_credits = getattr(settings, "referral_register_reward_credits", 50)
    if reward_credits <= 0:
        return

    expires_at = now_bj() + timedelta(days=settings.sign_in_reward_expire_days)
    await earn_credits(
        db=db,
        user_id=user.invited_by,
        amount=reward_credits,
        source="gift",
        expires_at=expires_at,
        remark=f"邀请好友注册奖励（用户 {user.id}）",
    )


async def reward_inviter_on_first_purchase(db: AsyncSession, user: User) -> None:
    """被邀请人首次购买后给邀请人发积分奖励。"""
    if not user.invited_by:
        return

    reward_credits = getattr(settings, "referral_purchase_reward_credits", 100)
    if reward_credits <= 0:
        return

    expires_at = now_bj() + timedelta(days=settings.sign_in_reward_expire_days)
    await earn_credits(
        db=db,
        user_id=user.invited_by,
        amount=reward_credits,
        source="gift",
        expires_at=expires_at,
        remark=f"邀请好友首次购买奖励（用户 {user.id}）",
    )
