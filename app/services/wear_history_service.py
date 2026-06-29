from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj
from app.models.item import Item
from app.models.wear_history import WearHistory
from app.schemas.common import ItemEntry
from app.schemas.wear_history import WearHistoryCreate

_WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


def _weekday_cn(d: date) -> str:
    return _WEEKDAYS[d.weekday()]


def _item_entry(item: Item) -> ItemEntry:
    return ItemEntry(
        id=item.id,
        name=item.name,
        category=item.category,
        image_url=item.image_url or "",
        image_color=item.image_color,
        thumbnail_url=item.thumbnail_url,
    )


async def _item_map(
    db: AsyncSession, user_id: UUID, item_ids: list[UUID]
) -> dict[UUID, Item]:
    if not item_ids:
        return {}
    result = await db.execute(
        select(Item).where(
            Item.id.in_(item_ids),
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return {item.id: item for item in result.scalars().all()}


def _history_out(history: WearHistory, items: dict[UUID, Item]) -> dict:
    return {
        "id": history.id,
        "date": history.date.isoformat(),
        "weekday": _weekday_cn(history.date),
        "weather": history.weather,
        "occasion": history.occasion,
        "itemIds": history.item_ids,
        "items": [
            _item_entry(items[item_id]).model_dump(by_alias=True)
            for item_id in history.item_ids
            if item_id in items
        ],
        "note": history.note,
        "createdAt": history.created_at,
    }


async def create_history(
    db: AsyncSession, user_id: UUID, data: WearHistoryCreate
) -> WearHistory:
    if not data.item_ids:
        raise BadRequestException("请至少选择一件衣物")

    # 校验所有衣物属于当前用户且未删除
    items = await _item_map(db, user_id, data.item_ids)
    if len(items) != len(data.item_ids):
        raise BadRequestException("部分衣物不存在或无权访问")

    history = WearHistory(
        user_id=user_id,
        date=data.date,
        weather=data.weather,
        occasion=data.occasion,
        item_ids=data.item_ids,
        note=data.note,
    )
    db.add(history)

    # 同步更新穿着统计
    await db.execute(
        update(Item)
        .where(Item.id.in_(data.item_ids), Item.user_id == user_id)
        .values(wear_count=Item.wear_count + 1, last_worn_at=now_bj())
    )

    await db.commit()
    await db.refresh(history)
    return history


async def list_history(
    db: AsyncSession,
    user_id: UUID,
    occasion: str | None = None,
    start_date: date | None = None,
) -> list[WearHistory]:
    stmt = (
        select(WearHistory)
        .where(WearHistory.user_id == user_id)
        .order_by(WearHistory.date.desc())
    )
    if occasion and occasion != "all":
        stmt = stmt.where(WearHistory.occasion == occasion)
    if start_date:
        stmt = stmt.where(WearHistory.date >= start_date)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def recent_history(
    db: AsyncSession, user_id: UUID, days: int = 7
) -> list[WearHistory]:
    start = (now_bj().date() - timedelta(days=days))
    return await list_history(db, user_id, start_date=start)


async def build_history_list_response(
    db: AsyncSession, user_id: UUID, histories: list[WearHistory]
) -> list[dict]:
    all_item_ids = set()
    for h in histories:
        all_item_ids.update(h.item_ids)
    items = await _item_map(db, user_id, list(all_item_ids))
    return [_history_out(h, items) for h in histories]
