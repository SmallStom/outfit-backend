from datetime import date
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import now_bj
from app.models.item import Item


_CATEGORY_META = {
    "top": {"label": "上装", "color": "#1a1a1a"},
    "bottom": {"label": "下装", "color": "#4a4a4a"},
    "outer": {"label": "外套", "color": "#888888"},
    "shoes": {"label": "鞋履", "color": "#bbbbbb"},
    "acc": {"label": "配饰", "color": "#dddddd"},
}


def _price(item: Item) -> int:
    return item.price or 0


async def _user_items(db: AsyncSession, user_id: UUID) -> list[Item]:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def overview(db: AsyncSession, user_id: UUID) -> dict:
    items = await _user_items(db, user_id)
    total_value = sum(_price(item) for item in items)
    total_count = len(items)
    total_wear = sum(item.wear_count or 0 for item in items)

    earliest_purchase = min(
        (item.purchase_date for item in items if item.purchase_date),
        default=now_bj().date(),
    )
    months = max(1, (now_bj().date() - earliest_purchase).days // 30 + 1)
    monthly_cost = int(total_value / months)
    avg_cost_per_wear = int(total_value / total_wear) if total_wear else 0

    brand_counts: dict[str, int] = {}
    for item in items:
        if item.brand:
            brand_counts[item.brand] = brand_counts.get(item.brand, 0) + 1
    top_brand = max(brand_counts, key=brand_counts.get) if brand_counts else None

    return {
        "total_value": total_value,
        "total_count": total_count,
        "monthly_cost": monthly_cost,
        "avg_cost_per_wear": avg_cost_per_wear,
        "top_brand": top_brand,
    }


async def category_distribution(db: AsyncSession, user_id: UUID) -> list[dict]:
    items = await _user_items(db, user_id)
    total_value = sum(_price(item) for item in items)
    groups: dict[str, dict] = {}
    for item in items:
        meta = _CATEGORY_META.get(item.category, {"label": item.category, "color": "#999999"})
        if item.category not in groups:
            groups[item.category] = {
                "category": item.category,
                "label": meta["label"],
                "color": meta["color"],
                "count": 0,
                "value": 0,
            }
        groups[item.category]["count"] += 1
        groups[item.category]["value"] += _price(item)

    result = []
    for cat in ["top", "bottom", "outer", "shoes", "acc"]:
        if cat not in groups:
            meta = _CATEGORY_META[cat]
            groups[cat] = {
                "category": cat,
                "label": meta["label"],
                "color": meta["color"],
                "count": 0,
                "value": 0,
            }
        group = groups[cat]
        group["percent"] = int(group["value"] / total_value * 100) if total_value else 0
        result.append(group)
    return result


async def idle_items(db: AsyncSession, user_id: UUID, days: int = 30) -> list[dict]:
    items = await _user_items(db, user_id)
    today = now_bj().date()
    idle = []
    for item in items:
        if item.last_worn_at:
            last = item.last_worn_at.date() if hasattr(item.last_worn_at, "date") else item.last_worn_at
            idle_days = (today - last).days
        elif item.purchase_date:
            idle_days = (today - item.purchase_date).days
        else:
            continue
        if idle_days >= days:
            idle.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "thumbnail_color": item.image_color,
                    "image_url": item.image_url or "",
                    "idle_days": idle_days,
                    "price": _price(item),
                    "purchase_date": (
                        item.purchase_date.strftime("%Y-%m")
                        if item.purchase_date
                        else None
                    ),
                }
            )
    idle.sort(key=lambda x: x["idle_days"], reverse=True)
    return idle


async def cost_per_wear(db: AsyncSession, user_id: UUID, limit: int = 10) -> list[dict]:
    items = await _user_items(db, user_id)
    rows = []
    for item in items:
        wear = item.wear_count or 0
        if wear == 0:
            continue
        cost = int(_price(item) / wear)
        rows.append(
            {
                "name": item.name,
                "cost": cost,
                "brand": item.brand,
                "wear_count": wear,
            }
        )
    rows.sort(key=lambda x: x["cost"], reverse=True)

    if not rows:
        return []

    max_cost = rows[0]["cost"]
    min_cost = rows[-1]["cost"]
    span = max_cost - min_cost or 1

    result = []
    for rank, row in enumerate(rows[:limit], start=1):
        percent = int(100 - (row["cost"] - min_cost) / span * 100)
        percent = max(5, min(100, percent))
        result.append(
            {
                "rank": rank,
                "name": row["name"],
                "cost": row["cost"],
                "percent": percent,
                "brand": row["brand"],
                "wear_count": row["wear_count"],
            }
        )
    return result
