"""用前端 mock 数据初始化数据库。

运行前确保：
1. .env 中 DATABASE_URL 配置正确
2. 已执行 alembic upgrade head 创建表

用法：
    python scripts/init_mock_data.py
"""
import asyncio
import json
import os
import sys
from datetime import date, datetime
from uuid import UUID, uuid4

# 把项目根目录加入 Python 路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

# 加载后端 .env
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.tryon_preset import TryonPreset
from app.models.user import User

MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), "mock_data.json")


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    # mock 里只有日期字符串，按当天 00:00:00 处理
    return datetime.strptime(value, "%Y-%m-%d")


async def ensure_user(db: AsyncSession) -> User:
    """创建或获取一个 mock 用户，所有衣物都挂在这个用户下。"""
    result = await db.execute(select(User).where(User.openid == "mock_user_001"))
    user = result.scalar_one_or_none()
    if user:
        print(f"use existing mock user: {user.id}")
        return user

    user = User(
        id=uuid4(),
        openid="mock_user_001",
        phone="13800138000",
        nickname="Mock User",
        avatar_url="https://picsum.photos/seed/mock-user/200/200",
        avatar_color="#e8d5c4",
        bio="前端 mock 数据初始化用户",
        gender="unknown",
    )
    db.add(user)
    await db.flush()
    print(f"created mock user: {user.id}")
    return user


async def init_items(db: AsyncSession, user_id: UUID) -> dict[str, UUID]:
    """导入 mock 衣物，返回 mock_id -> db_id 映射。"""
    with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    mock_items = data["items"]
    id_map: dict[str, UUID] = {}

    # 先清空该用户的旧数据（可选，方便重复执行）
    result = await db.execute(select(Item).where(Item.user_id == user_id))
    for existing in result.scalars().all():
        await db.delete(existing)
    await db.flush()
    print("cleared existing mock items")

    for mock_item in mock_items:
        db_item = Item(
            id=uuid4(),
            user_id=user_id,
            name=mock_item["name"],
            category=mock_item["category"],
            sub_category=None,
            image_url=mock_item.get("imageUrl", ""),
            thumbnail_url=None,
            image_color=mock_item.get("imageColor"),
            price=mock_item.get("price"),
            brand=mock_item.get("brand"),
            material=mock_item.get("material"),
            color=mock_item.get("color"),
            color_hex=mock_item.get("colorHex"),
            season=mock_item.get("season"),
            care_method=mock_item.get("careMethod"),
            care_detail=mock_item.get("careDetail"),
            occasion=None,
            purchase_date=parse_date(mock_item.get("purchaseDate")),
            wear_count=mock_item.get("wearCount", 0),
            last_worn_at=parse_datetime(mock_item.get("lastWornAt")),
            tags=mock_item.get("tags", []),
            is_deleted=False,
        )
        db.add(db_item)
        id_map[mock_item["id"]] = db_item.id

    await db.flush()
    print(f"initialized {len(id_map)} items")
    return id_map


async def init_tryon_presets(
    db: AsyncSession, user_id: UUID, id_map: dict[str, UUID]
) -> None:
    """导入 mock 试衣预设。"""
    with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    mock_presets = data["presets"]

    # 清空旧预设
    result = await db.execute(
        select(TryonPreset).where(TryonPreset.user_id == user_id)
    )
    for existing in result.scalars().all():
        await db.delete(existing)
    await db.flush()
    print("cleared existing mock tryon presets")

    for mock_preset in mock_presets:
        item_ids = [
            id_map[item_id]
            for item_id in mock_preset["items"]
            if item_id in id_map
        ]
        preset = TryonPreset(
            id=uuid4(),
            user_id=user_id,
            name=mock_preset["name"],
            occasion=mock_preset.get("occasion"),
            item_ids=item_ids,
        )
        db.add(preset)

    await db.flush()
    print(f"initialized {len(mock_presets)} tryon presets")


async def main() -> None:
    async with AsyncSessionLocal() as db:
        user = await ensure_user(db)
        id_map = await init_items(db, user.id)
        await init_tryon_presets(db, user.id, id_map)
        await db.commit()
        print("mock data initialized successfully")


if __name__ == "__main__":
    asyncio.run(main())
