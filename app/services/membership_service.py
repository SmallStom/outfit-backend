from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.timezone import now_bj
from app.models.membership import MembershipTier, UserMembership


async def list_active_tiers(db: AsyncSession) -> list[MembershipTier]:
    result = await db.execute(
        select(MembershipTier)
        .where(MembershipTier.is_active.is_(True))
        .order_by(MembershipTier.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_tier(db: AsyncSession, tier_id: UUID) -> MembershipTier:
    result = await db.execute(select(MembershipTier).where(MembershipTier.id == tier_id))
    tier = result.scalar_one_or_none()
    if tier is None:
        raise NotFoundException("会员档位不存在")
    return tier


async def get_user_membership(db: AsyncSession, user_id: UUID) -> UserMembership | None:
    now = now_bj()
    result = await db.execute(
        select(UserMembership)
        .options(selectinload(UserMembership.tier))
        .where(
            UserMembership.user_id == user_id,
            UserMembership.status == "active",
            UserMembership.expired_at > now,
            UserMembership.started_at <= now,
        )
        .order_by(UserMembership.expired_at.desc())
    )
    return result.scalar_one_or_none()


async def check_membership_quota(
    db: AsyncSession, user_id: UUID, feature: str
) -> dict:
    """返回会员某功能的剩余次数。

    feature: "tryon" | "puzzle"
    返回: {"has_quota": bool, "remaining": int, "total": int, "used": int}
    """
    membership = await get_user_membership(db, user_id)
    if membership is None:
        return {"has_quota": False, "remaining": 0, "total": 0, "used": 0}

    tier = membership.tier
    if feature == "tryon":
        total = tier.ai_tryon_quota
        used = membership.ai_tryon_used
    elif feature == "puzzle":
        total = tier.puzzle_quota
        used = membership.puzzle_used
    else:
        raise BadRequestException(f"未知功能类型: {feature}")

    remaining = max(0, total - used)
    return {"has_quota": remaining > 0, "remaining": remaining, "total": total, "used": used}


async def deduct_membership_quota(
    db: AsyncSession, user_id: UUID, feature: str
) -> bool:
    """扣减会员次数，返回是否成功。"""
    now = now_bj()
    if feature not in ("tryon", "puzzle"):
        raise BadRequestException(f"未知功能类型: {feature}")

    result = await db.execute(
        select(UserMembership)
        .where(
            UserMembership.user_id == user_id,
            UserMembership.status == "active",
            UserMembership.expired_at > now,
            UserMembership.started_at <= now,
        )
        .with_for_update()
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        return False

    await db.refresh(membership, ["tier"])
    tier = membership.tier
    if feature == "tryon":
        total = tier.ai_tryon_quota
        remaining = total - membership.ai_tryon_used
        if remaining <= 0:
            return False
        membership.ai_tryon_used += 1
    else:
        total = tier.puzzle_quota
        remaining = total - membership.puzzle_used
        if remaining <= 0:
            return False
        membership.puzzle_used += 1

    await db.commit()
    return True


async def activate_membership(
    db: AsyncSession,
    user_id: UUID,
    tier_id: UUID,
    duration_months: int,
    is_new_user_price: bool = False,
) -> UserMembership:
    """根据订单开通会员。若已有生效会员则顺延过期时间。"""
    tier = await get_tier(db, tier_id)

    now = now_bj()
    existing = await get_user_membership(db, user_id)
    if existing:
        started_at = existing.started_at
        expired_at = existing.expired_at + timedelta(days=30 * duration_months)
        # 将旧会员标记为已续期，实际应用中可保留历史记录；这里简单更新过期时间
        existing.expired_at = expired_at
        existing.updated_at = now
        await db.commit()
        await db.refresh(existing)
        return existing

    started_at = now
    expired_at = now + timedelta(days=30 * duration_months)

    membership = UserMembership(
        user_id=user_id,
        tier_id=tier_id,
        started_at=started_at,
        expired_at=expired_at,
        status="active",
        ai_tryon_used=0,
        puzzle_used=0,
    )
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership


async def expire_memberships(db: AsyncSession) -> int:
    """将已过期的会员状态更新为 expired，返回更新数量。"""
    now = now_bj()
    from sqlalchemy import update

    result = await db.execute(
        update(UserMembership)
        .where(
            UserMembership.status == "active",
            UserMembership.expired_at <= now,
        )
        .values(status="expired")
    )
    await db.commit()
    return result.rowcount or 0
