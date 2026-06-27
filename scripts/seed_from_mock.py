"""将前端 mock 数据样例导入后端数据库（开发测试用）。"""

import asyncio
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select

from app.core.timezone import BEIJING_TZ
from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.user import User

# 从 miniprogram/mock/items.js 中提取的部分样例数据
SAMPLE_ITEMS = [
    {
        "name": "白色棉质T恤",
        "category": "top",
        "imageColor": "#f0ece6",
        "price": 199,
        "brand": "UNIQLO",
        "material": "100% 棉",
        "color": "白色",
        "colorHex": "#FFFFFF",
        "season": "春夏",
        "tags": ["T恤", "白色", "纯棉", "基础款", "休闲"],
        "careMethod": "machine_wash",
        "careDetail": "30°C 机洗，不可漂白",
        "purchaseDate": "2024-03-15",
        "wearCount": 28,
        "lastWornAt": "2026-06-20",
    },
    {
        "name": "原色直筒牛仔裤",
        "category": "bottom",
        "imageColor": "#ebe8e5",
        "price": 1290,
        "brand": "Levis",
        "material": "98% 棉 2% 氨纶",
        "color": "蓝色",
        "colorHex": "#5a7fa8",
        "season": "四季",
        "tags": ["牛仔裤", "蓝色", "直筒", "休闲"],
        "careMethod": "machine_wash",
        "careDetail": "冷水机洗，反面清洗",
        "purchaseDate": "2024-01-08",
        "wearCount": 42,
        "lastWornAt": "2026-06-22",
    },
    {
        "name": "极简灰色运动鞋",
        "category": "shoes",
        "imageColor": "#f2f0ec",
        "price": 899,
        "brand": "New Balance",
        "material": "网面 + 合成革",
        "color": "灰色",
        "colorHex": "#c8c4bc",
        "season": "四季",
        "tags": ["运动鞋", "灰色", "休闲"],
        "careMethod": "hand_wash",
        "careDetail": "湿布擦拭，阴干",
        "purchaseDate": "2024-02-20",
        "wearCount": 56,
        "lastWornAt": "2026-06-24",
    },
]


def _to_date(value: str | None) -> date | None:
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=BEIJING_TZ)


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.openid == "dev-user-1"))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(openid="dev-user-1", nickname="Alex Chen")
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"创建用户: {user.id}")
        else:
            print(f"用户已存在: {user.id}")

        for data in SAMPLE_ITEMS:
            item = Item(
                user_id=user.id,
                name=data["name"],
                category=data["category"],
                image_color=data.get("imageColor"),
                price=data.get("price"),
                brand=data.get("brand"),
                material=data.get("material"),
                color=data.get("color"),
                color_hex=data.get("colorHex"),
                season=data.get("season"),
                tags=data.get("tags", []),
                care_method=data.get("careMethod"),
                care_detail=data.get("careDetail"),
                purchase_date=_to_date(data.get("purchaseDate")),
                wear_count=data.get("wearCount", 0),
                last_worn_at=_to_datetime(data.get("lastWornAt")),
                image_url="",
                is_deleted=False,
            )
            db.add(item)

        await db.commit()
        print(f"已导入 {len(SAMPLE_ITEMS)} 件衣物")


if __name__ == "__main__":
    asyncio.run(seed())
