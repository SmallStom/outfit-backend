from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.timezone import now_bj
from app.models.item import Item
from app.models.outfit import Outfit, OutfitCollection, OutfitCollectionItem, OutfitItem
from app.schemas.outfit import (
    OutfitCollectionCreate,
    OutfitCollectionUpdate,
    OutfitCreate,
    OutfitItemEntry,
    OutfitUpdate,
)


def _item_entry(item: Item) -> OutfitItemEntry:
    return OutfitItemEntry(
        id=item.id,
        name=item.name,
        category=item.category,
        image_url=item.image_url or "",
        image_color=item.image_color,
        thumbnail_url=item.thumbnail_url,
    )


async def _validate_item_ids(
    db: AsyncSession, user_id: UUID, item_ids: list[UUID]
) -> list[Item]:
    if not item_ids:
        return []
    unique_ids = list(dict.fromkeys(item_ids))
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.id.in_(unique_ids),
            Item.is_deleted.is_(False),
        )
    )
    items = list(result.scalars().all())
    if len(items) != len(unique_ids):
        raise NotFoundException("部分衣物不存在或已删除")
    return items


async def create_outfit(
    db: AsyncSession, user_id: UUID, data: OutfitCreate
) -> Outfit:
    await _validate_item_ids(db, user_id, data.item_ids)
    outfit_data = data.model_dump(exclude={"item_ids"})
    outfit = Outfit(user_id=user_id, **outfit_data)
    db.add(outfit)
    await db.flush()
    for sort_order, item_id in enumerate(data.item_ids):
        db.add(
            OutfitItem(
                outfit_id=outfit.id, item_id=item_id, sort_order=sort_order
            )
        )
    await db.commit()
    await db.refresh(outfit)
    return outfit


async def list_outfits(
    db: AsyncSession, user_id: UUID, ai_only: bool | None = None
) -> list[Outfit]:
    stmt = (
        select(Outfit)
        .where(Outfit.user_id == user_id)
        .order_by(Outfit.created_at.desc())
    )
    if ai_only is not None:
        stmt = stmt.where(Outfit.is_ai_generated.is_(ai_only))
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_outfit(db: AsyncSession, user_id: UUID, outfit_id: UUID) -> Outfit:
    result = await db.execute(
        select(Outfit).where(Outfit.id == outfit_id, Outfit.user_id == user_id)
    )
    outfit = result.scalar_one_or_none()
    if outfit is None:
        raise NotFoundException("搭配方案不存在")
    return outfit


async def update_outfit(
    db: AsyncSession, user_id: UUID, outfit_id: UUID, data: OutfitUpdate
) -> Outfit:
    outfit = await get_outfit(db, user_id, outfit_id)
    update_data = data.model_dump(exclude={"item_ids"}, exclude_unset=True)
    for key, value in update_data.items():
        setattr(outfit, key, value)

    if data.item_ids is not None:
        await _validate_item_ids(db, user_id, data.item_ids)
        # 删除旧关联
        for old in outfit.items:
            await db.delete(old)
        await db.flush()
        for sort_order, item_id in enumerate(data.item_ids):
            db.add(
                OutfitItem(
                    outfit_id=outfit.id,
                    item_id=item_id,
                    sort_order=sort_order,
                )
            )

    await db.commit()
    await db.refresh(outfit)
    return outfit


async def delete_outfit(db: AsyncSession, user_id: UUID, outfit_id: UUID) -> None:
    outfit = await get_outfit(db, user_id, outfit_id)
    await db.delete(outfit)
    await db.commit()


async def recommend_outfit(db: AsyncSession, user_id: UUID) -> Outfit:
    """规则版 AI 推荐：从用户衣橱中按分类各选一件组成搭配。"""
    categories = ["top", "bottom", "shoes", "outer", "acc"]
    selected_item_ids: list[UUID] = []
    for category in categories:
        result = await db.execute(
            select(Item)
            .where(
                Item.user_id == user_id,
                Item.category == category,
                Item.is_deleted.is_(False),
            )
            .order_by(func.random())
            .limit(1)
        )
        item = result.scalar_one_or_none()
        if item:
            selected_item_ids.append(item.id)

    if not selected_item_ids:
        raise BadRequestException("衣橱为空，无法生成推荐搭配")

    outfit = Outfit(
        user_id=user_id,
        name="AI 今日推荐",
        occasion="日常",
        weather="晴 22°C",
        is_ai_generated=True,
        color_scheme=["#1a1a1a", "#888888", "#cccccc"],
    )
    db.add(outfit)
    await db.flush()
    for sort_order, item_id in enumerate(selected_item_ids):
        db.add(
            OutfitItem(
                outfit_id=outfit.id, item_id=item_id, sort_order=sort_order
            )
        )
    await db.commit()
    await db.refresh(outfit)
    return outfit


# ---------------------------- 搭配集 ----------------------------


async def create_collection(
    db: AsyncSession, user_id: UUID, data: OutfitCollectionCreate
) -> OutfitCollection:
    await _validate_item_ids(db, user_id, data.item_ids)
    collection_data = data.model_dump(exclude={"item_ids"})
    collection = OutfitCollection(user_id=user_id, **collection_data)
    db.add(collection)
    await db.flush()
    for sort_order, item_id in enumerate(data.item_ids):
        db.add(
            OutfitCollectionItem(
                collection_id=collection.id,
                item_id=item_id,
                sort_order=sort_order,
            )
        )
    await db.commit()
    await db.refresh(collection)
    return collection


async def list_collections(
    db: AsyncSession, user_id: UUID
) -> list[OutfitCollection]:
    result = await db.execute(
        select(OutfitCollection)
        .where(OutfitCollection.user_id == user_id)
        .order_by(OutfitCollection.updated_at.desc())
    )
    return list(result.scalars().all())


async def get_collection(
    db: AsyncSession, user_id: UUID, collection_id: UUID
) -> OutfitCollection:
    result = await db.execute(
        select(OutfitCollection).where(
            OutfitCollection.id == collection_id,
            OutfitCollection.user_id == user_id,
        )
    )
    collection = result.scalar_one_or_none()
    if collection is None:
        raise NotFoundException("搭配集不存在")
    return collection


async def update_collection(
    db: AsyncSession,
    user_id: UUID,
    collection_id: UUID,
    data: OutfitCollectionUpdate,
) -> OutfitCollection:
    collection = await get_collection(db, user_id, collection_id)
    update_data = data.model_dump(exclude={"item_ids"}, exclude_unset=True)
    for key, value in update_data.items():
        setattr(collection, key, value)

    if data.item_ids is not None:
        await _validate_item_ids(db, user_id, data.item_ids)
        for old in collection.items:
            await db.delete(old)
        await db.flush()
        for sort_order, item_id in enumerate(data.item_ids):
            db.add(
                OutfitCollectionItem(
                    collection_id=collection.id,
                    item_id=item_id,
                    sort_order=sort_order,
                )
            )

    collection.updated_at = now_bj()
    await db.commit()
    await db.refresh(collection)
    return collection


async def delete_collection(
    db: AsyncSession, user_id: UUID, collection_id: UUID
) -> None:
    collection = await get_collection(db, user_id, collection_id)
    await db.delete(collection)
    await db.commit()
