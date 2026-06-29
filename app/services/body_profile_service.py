from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.body_profile import BodyProfile
from app.schemas.body_profile import BodyProfileCreate, BodyProfileUpdate

BODY_TYPES = [
    {"key": "standard", "label": "标准型", "desc": "肩腰臀比例均衡，适合大多数版型"},
    {"key": "inverted-triangle", "label": "倒三角型", "desc": "肩宽腰细，适合V领、收腰款式"},
    {"key": "pear", "label": "梨形", "desc": "上半身瘦、臀宽，适合A字裙、高腰裤"},
    {"key": "apple", "label": "苹果型", "desc": "腰腹较宽，适合宽松上衣、直筒裤"},
    {"key": "rectangle", "label": "直筒型", "desc": "肩腰臀接近，适合有腰线的款式"},
]


async def create_profile(
    db: AsyncSession, user_id: UUID, data: BodyProfileCreate
) -> BodyProfile:
    profile_data = data.model_dump()
    profile = BodyProfile(user_id=user_id, **profile_data)
    db.add(profile)
    await db.flush()
    if profile.is_active:
        await db.execute(
            update(BodyProfile)
            .where(
                BodyProfile.user_id == user_id,
                BodyProfile.id != profile.id,
                BodyProfile.is_active.is_(True),
            )
            .values(is_active=False)
        )
    await db.commit()
    await db.refresh(profile)
    return profile


async def list_profiles(db: AsyncSession, user_id: UUID) -> list[BodyProfile]:
    result = await db.execute(
        select(BodyProfile)
        .where(BodyProfile.user_id == user_id)
        .order_by(BodyProfile.created_at.desc())
    )
    return list(result.scalars().all())


async def get_profile(
    db: AsyncSession, user_id: UUID, profile_id: UUID
) -> BodyProfile:
    result = await db.execute(
        select(BodyProfile).where(
            BodyProfile.id == profile_id,
            BodyProfile.user_id == user_id,
        )
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise NotFoundException("身材档案不存在")
    return profile


async def update_profile(
    db: AsyncSession,
    user_id: UUID,
    profile_id: UUID,
    data: BodyProfileUpdate,
) -> BodyProfile:
    profile = await get_profile(db, user_id, profile_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(profile, key, value)
    if data.is_active:
        await db.execute(
            update(BodyProfile)
            .where(
                BodyProfile.user_id == user_id,
                BodyProfile.id != profile_id,
                BodyProfile.is_active.is_(True),
            )
            .values(is_active=False)
        )
    await db.commit()
    await db.refresh(profile)
    return profile


async def delete_profile(
    db: AsyncSession, user_id: UUID, profile_id: UUID
) -> None:
    profile = await get_profile(db, user_id, profile_id)
    await db.delete(profile)
    await db.commit()


async def activate_profile(
    db: AsyncSession, user_id: UUID, profile_id: UUID
) -> BodyProfile:
    profile = await get_profile(db, user_id, profile_id)
    await db.execute(
        update(BodyProfile)
        .where(
            BodyProfile.user_id == user_id,
            BodyProfile.id != profile_id,
            BodyProfile.is_active.is_(True),
        )
        .values(is_active=False)
    )
    profile.is_active = True
    await db.commit()
    await db.refresh(profile)
    return profile
