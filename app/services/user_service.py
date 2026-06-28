from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.follow import UserFollow
from app.models.item import Item
from app.models.outfit import Outfit, OutfitCollection
from app.models.post import Post
from app.models.settings import UserSettings
from app.models.user import User


def _user_list_item(user: User) -> dict:
    return {
        "id": user.id,
        "nickname": user.nickname or f"用户{str(user.id)[:4]}",
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color,
    }


async def _get_user(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    return user


async def get_user_stats(db: AsyncSession, user_id: UUID) -> dict:
    item_result = await db.execute(
        select(func.count())
        .select_from(Item)
        .where(Item.user_id == user_id, Item.is_deleted.is_(False))
    )
    item_count = item_result.scalar() or 0

    outfit_result = await db.execute(
        select(func.count()).select_from(Outfit).where(Outfit.user_id == user_id)
    )
    outfit_count = outfit_result.scalar() or 0

    collection_result = await db.execute(
        select(func.count())
        .select_from(OutfitCollection)
        .where(OutfitCollection.user_id == user_id)
    )
    collection_count = collection_result.scalar() or 0

    like_result = await db.execute(
        select(func.coalesce(func.sum(Post.like_count), 0)).where(
            Post.user_id == user_id
        )
    )
    like_received_count = like_result.scalar() or 0

    followers_result = await db.execute(
        select(func.count()).select_from(UserFollow).where(
            UserFollow.following_id == user_id
        )
    )
    followers_count = followers_result.scalar() or 0

    following_result = await db.execute(
        select(func.count()).select_from(UserFollow).where(
            UserFollow.follower_id == user_id
        )
    )
    following_count = following_result.scalar() or 0

    return {
        "item_count": item_count,
        "outfit_count": outfit_count,
        "outfit_collection_count": collection_count,
        "like_received_count": like_received_count,
        "followers_count": followers_count,
        "following_count": following_count,
    }


async def toggle_follow(
    db: AsyncSession, current_user_id: UUID, target_user_id: UUID
) -> dict:
    if current_user_id == target_user_id:
        raise BadRequestException("不能关注自己")

    await _get_user(db, target_user_id)

    result = await db.execute(
        select(UserFollow).where(
            UserFollow.follower_id == current_user_id,
            UserFollow.following_id == target_user_id,
        )
    )
    follow = result.scalar_one_or_none()

    if follow:
        await db.delete(follow)
        is_following = False
    else:
        db.add(
            UserFollow(follower_id=current_user_id, following_id=target_user_id)
        )
        is_following = True

    await db.commit()
    return {"is_following": is_following}


async def list_followers(
    db: AsyncSession, user_id: UUID
) -> list[dict]:
    result = await db.execute(
        select(User)
        .join(UserFollow, UserFollow.follower_id == User.id)
        .where(UserFollow.following_id == user_id)
        .order_by(UserFollow.created_at.desc())
    )
    return [_user_list_item(u) for u in result.scalars().all()]


async def list_following(
    db: AsyncSession, user_id: UUID
) -> list[dict]:
    result = await db.execute(
        select(User)
        .join(UserFollow, UserFollow.following_id == User.id)
        .where(UserFollow.follower_id == user_id)
        .order_by(UserFollow.created_at.desc())
    )
    return [_user_list_item(u) for u in result.scalars().all()]


async def get_or_create_settings(
    db: AsyncSession, user_id: UUID
) -> UserSettings:
    result = await db.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()
    if settings is None:
        settings = UserSettings(user_id=user_id)
        db.add(settings)
        await db.commit()
        await db.refresh(settings)
    return settings


async def update_settings(
    db: AsyncSession, user_id: UUID, notification_prefs: dict | None, privacy_prefs: dict | None
) -> UserSettings:
    settings = await get_or_create_settings(db, user_id)
    if notification_prefs is not None:
        settings.notification_prefs = notification_prefs
    if privacy_prefs is not None:
        settings.privacy_prefs = privacy_prefs
    await db.commit()
    await db.refresh(settings)
    return settings
