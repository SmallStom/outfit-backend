from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_bj
from app.models.membership import UserMembership
from app.models.user import User


async def get_expiring_memberships(
    db: AsyncSession, days: int = 3
) -> list[dict]:
    """查询指定天数内即将到期的会员。"""
    now = now_bj()
    deadline = now + timedelta(days=days)

    result = await db.execute(
        select(UserMembership, User)
        .join(User, UserMembership.user_id == User.id)
        .where(
            UserMembership.is_active.is_(True),
            UserMembership.expired_at > now,
            UserMembership.expired_at <= deadline,
        )
        .order_by(UserMembership.expired_at.asc())
    )

    return [
        {
            "user_id": user.id,
            "nickname": user.nickname,
            "expired_at": membership.expired_at,
            "days_left": (membership.expired_at - now).days,
        }
        for membership, user in result.unique().all()
    ]


async def get_user_membership_reminder(
    db: AsyncSession, user_id: UUID
) -> dict | None:
    """查询当前用户的会员到期提醒。"""
    now = now_bj()
    result = await db.execute(
        select(UserMembership).where(
            UserMembership.user_id == user_id,
            UserMembership.is_active.is_(True),
            UserMembership.expired_at > now,
        )
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return None

    days_left = (membership.expired_at - now).days
    if days_left > 7:
        return None

    return {
        "expired_at": membership.expired_at,
        "days_left": days_left,
        "should_remind": days_left <= 3,
    }
