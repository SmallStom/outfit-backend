from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AIException
from app.models.item import Item
from app.models.tryon_preset import TryonPreset

_CATEGORIES = [
    {"key": "top", "label": "上装"},
    {"key": "bottom", "label": "下装"},
    {"key": "dress", "label": "裙装"},
    {"key": "outer", "label": "外套"},
    {"key": "shoes", "label": "鞋履"},
    {"key": "acc", "label": "配饰"},
]

_PRESET_RULES = [
    {
        "id": "preset-1",
        "name": "商务通勤",
        "occasion": "通勤",
        "items": {
            "top": 1,
            "bottom": 1,
            "outer": 1,
            "shoes": 1,
            "acc": 1,
        },
    },
    {
        "id": "preset-2",
        "name": "周末休闲",
        "occasion": "休闲",
        "items": {
            "top": 1,
            "bottom": 1,
            "shoes": 1,
        },
    },
    {
        "id": "preset-3",
        "name": "约会优雅",
        "occasion": "约会",
        "items": {
            "top": 1,
            "bottom": 1,
            "outer": 1,
            "shoes": 1,
            "acc": 1,
        },
    },
    {
        "id": "preset-4",
        "name": "街头潮流",
        "occasion": "休闲",
        "items": {
            "top": 1,
            "bottom": 1,
            "shoes": 1,
        },
    },
]


async def items_by_category(
    db: AsyncSession, user_id: UUID, category: str
) -> list[Item]:
    stmt = (
        select(Item)
        .where(
            Item.user_id == user_id,
            Item.category == category,
            Item.is_deleted.is_(False),
        )
        .order_by(Item.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def categories() -> list[dict]:
    return _CATEGORIES


def _pick_item(
    pool: list[Item], category: str, used_ids: set[UUID]
) -> Item | None:
    for item in pool:
        if item.category == category and item.id not in used_ids:
            used_ids.add(item.id)
            return item
    return None


async def generate_presets(
    db: AsyncSession, user_id: UUID
) -> list[dict]:
    items = await _all_items(db, user_id)
    presets = []
    for rule in _PRESET_RULES:
        used_ids: set[UUID] = set()
        preset_items = []
        for category in ["top", "bottom", "dress", "outer", "shoes", "acc"]:
            count = rule["items"].get(category, 0)
            for _ in range(count):
                item = _pick_item(items, category, used_ids)
                if item:
                    preset_items.append(item)
        # 兜底：每个预设至少放一件上装+下装
        if not preset_items:
            for cat in ["top", "bottom"]:
                item = _pick_item(items, cat, used_ids)
                if item:
                    preset_items.append(item)
        presets.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "occasion": rule["occasion"],
                "items": preset_items,
            }
        )
    return presets


async def _all_items(db: AsyncSession, user_id: UUID) -> list[Item]:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def list_presets(
    db: AsyncSession, user_id: UUID
) -> list[TryonPreset]:
    result = await db.execute(
        select(TryonPreset).where(
            (TryonPreset.user_id == user_id) | (TryonPreset.user_id.is_(None))
        )
    )
    return list(result.scalars().all())


async def generate_tryon(**kwargs) -> dict:
    # W3 占位：阿里云虚拟试衣需要 access key 与 SDK，后续接入
    raise AIException("虚拟试衣生成服务尚未配置")
