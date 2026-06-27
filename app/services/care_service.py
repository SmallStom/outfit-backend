from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.timezone import now_bj
from app.models.care_record import CareRecord
from app.models.item import Item


_CARE_RULES = {
    "dry_clean": {"max_days": 30, "max_wears": 5, "label": "干洗提醒", "verb": "送洗"},
    "hand_wash": {"max_days": 14, "max_wears": 3, "label": "手洗提醒", "verb": "手洗"},
    "machine_wash": {"max_days": 7, "max_wears": 3, "label": "常规洗护", "verb": "机洗"},
}


def _material_group(material: str | None) -> tuple[str, str, str]:
    m = material or ""
    if "羊毛" in m or "羊绒" in m:
        return "羊毛/羊绒", "#FF9500", "干洗提醒"
    if "真丝" in m:
        return "真丝", "#a855f7", "手洗提醒"
    if "皮" in m:
        return "皮革", "#8B4513", "专业护理"
    return "棉麻", "#34C759", "常规洗护"


def _care_info(item: Item) -> tuple[str, str, str, dict]:
    method = item.care_method or "machine_wash"
    category, color, _ = _material_group(item.material)
    rule = _CARE_RULES.get(method, _CARE_RULES["machine_wash"])
    label = rule["label"]
    if "皮" in (item.material or ""):
        label = "专业护理"
    return category, color, label, rule


def _reminder_for_item(
    item: Item, last_care_date: date | None
) -> dict:
    category, color, label, rule = _care_info(item)
    today = now_bj().date()

    if last_care_date:
        days_since = (today - last_care_date).days
    else:
        days_since = None

    wear_count = item.wear_count or 0

    done = False
    alert_type = "done"
    alert_message = "暂无需洗护"

    if days_since is not None and days_since > rule["max_days"]:
        alert_type = "overdue"
        alert_message = f"建议{rule['verb']}：已超期 {days_since - rule['max_days']} 天"
    elif wear_count >= rule["max_wears"]:
        alert_type = "wear_count"
        alert_message = f"建议{rule['verb']}：穿着已达 {wear_count} 次"
    elif days_since is not None and days_since <= rule["max_days"]:
        done = True
        alert_message = "已完成洗护或暂无需洗护"
    else:
        # 从未洗护但还没达到阈值，标记为完成态避免打扰
        done = True

    return {
        "item_id": item.id,
        "item_name": item.name,
        "thumbnail_color": item.image_color,
        "image_url": item.image_url or "",
        "last_care_date": last_care_date.isoformat() if last_care_date else "",
        "wear_count": wear_count,
        "alert_type": alert_type,
        "alert_message": alert_message,
        "care_method": item.care_method,
        "done": done,
        "_category": category,
        "_color": color,
        "_care_type": label,
    }


async def _latest_care_dates(
    db: AsyncSession, item_ids: list[UUID]
) -> dict[UUID, date]:
    if not item_ids:
        return {}
    stmt = (
        select(CareRecord.item_id, func.max(CareRecord.care_date).label("care_date"))
        .where(CareRecord.item_id.in_(item_ids))
        .group_by(CareRecord.item_id)
    )
    result = await db.execute(stmt)
    return {row.item_id: row.care_date for row in result.all()}


async def get_reminders(db: AsyncSession, user_id: UUID) -> dict:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
            Item.care_method.is_not(None),
        )
    )
    items = list(result.scalars().all())

    latest_dates = await _latest_care_dates(db, [item.id for item in items])

    groups_map: dict[str, dict] = {}
    pending_count = 0
    for item in items:
        reminder = _reminder_for_item(item, latest_dates.get(item.id))
        if not reminder["done"]:
            pending_count += 1
        key = reminder["_category"]
        if key not in groups_map:
            groups_map[key] = {
                "category": reminder["_category"],
                "color": reminder["_color"],
                "care_type": reminder["_care_type"],
                "items": [],
            }
        groups_map[key]["items"].append(
            {
                "item_id": reminder["item_id"],
                "item_name": reminder["item_name"],
                "thumbnail_color": reminder["thumbnail_color"],
                "image_url": reminder["image_url"],
                "last_care_date": reminder["last_care_date"],
                "wear_count": reminder["wear_count"],
                "alert_type": reminder["alert_type"],
                "alert_message": reminder["alert_message"],
                "care_method": reminder["care_method"],
                "done": reminder["done"],
            }
        )

    completed_this_month = await _completed_this_month(db, user_id)

    return {
        "stats": {
            "pending_count": pending_count,
            "completed_this_month": completed_this_month,
        },
        "groups": list(groups_map.values()),
    }


async def _completed_this_month(db: AsyncSession, user_id: UUID) -> int:
    today = now_bj().date()
    start_of_month = today.replace(day=1)
    stmt = (
        select(func.count(CareRecord.id))
        .join(Item, CareRecord.item_id == Item.id)
        .where(
            Item.user_id == user_id,
            CareRecord.care_date >= start_of_month,
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def mark_done(
    db: AsyncSession, user_id: UUID, item_id: UUID
) -> None:
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

    care_type = item.care_method or "machine_wash"
    record = CareRecord(
        item_id=item_id,
        care_type=care_type,
        care_date=now_bj().date(),
        notes="标记已完成洗护",
    )
    db.add(record)
    await db.commit()
