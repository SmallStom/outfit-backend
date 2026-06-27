from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.timezone import now_bj
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate
from app.schemas.wear_history import WearHistoryCreate
from app.services.wear_history_service import create_history


async def create_item(db: AsyncSession, user_id: UUID, data: ItemCreate) -> Item:
    item_data = data.model_dump()
    item = Item(user_id=user_id, wear_count=0, **item_data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_items(
    db: AsyncSession,
    user_id: UUID,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[Item]:
    stmt = (
        select(Item)
        .where(Item.user_id == user_id, Item.is_deleted.is_(False))
        .order_by(Item.created_at.desc())
    )
    if category and category != "all":
        stmt = stmt.where(Item.category == category)
    if tag:
        stmt = stmt.where(Item.tags.contains([tag]))
    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            or_(
                Item.name.ilike(q),
                Item.brand.ilike(q),
                Item.tags.any(search),
            )
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_item(db: AsyncSession, user_id: UUID, item_id: UUID) -> Item:
    result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("衣物不存在")
    return item


async def update_item(
    db: AsyncSession, user_id: UUID, item_id: UUID, data: ItemUpdate
) -> Item:
    item = await get_item(db, user_id, item_id)
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, user_id: UUID, item_id: UUID) -> None:
    item = await get_item(db, user_id, item_id)
    item.is_deleted = True
    await db.commit()


async def record_wear(db: AsyncSession, user_id: UUID, item_id: UUID) -> Item:
    item = await get_item(db, user_id, item_id)
    item.wear_count += 1
    item.last_worn_at = now_bj()
    await db.flush()
    await create_history(
        db=db,
        user_id=user_id,
        data=WearHistoryCreate(
            date=now_bj().date(),
            weather="",
            occasion="",
            item_ids=[item_id],
            note="记录穿着",
        ),
    )
    await db.commit()
    await db.refresh(item)
    return item


COMMON_TAGS = [
    "T恤", "衬衫", "毛衣", "开衫", "卫衣", "吊带", "Polo",
    "牛仔裤", "西裤", "半裙", "工装裤", "阔腿裤", "短裤",
    "风衣", "西装", "皮衣", "羽绒服", "外套",
    "运动鞋", "靴子", "小白鞋", "乐福鞋", "高跟鞋",
    "腰带", "围巾", "包包", "耳饰",
    "通勤", "休闲", "复古", "街头", "基础款", "修身", "宽松", "温柔", "优雅", "酷飒", "慵懒",
    "白色", "黑色", "蓝色", "绿色", "灰色", "米色", "驼色", "卡其",
    "纯棉", "羊绒", "真丝", "亚麻", "羊毛", "真皮",
]
