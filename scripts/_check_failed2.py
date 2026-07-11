"""查看失败 item 的完整错误信息和原始 VLM 返回。"""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.item import Item

# 用户提供的两个失败 ID（实际是同一个 ID 重复，查所有 failed）
FAILED_IDS = [
    "4c58ba40-92b0-493f-9bb4-a43674ae2bcd",
]

async def main():
    async with AsyncSessionLocal() as db:
        # 先查指定 ID
        for fid in FAILED_IDS:
            result = await db.execute(select(Item).where(Item.id == UUID(fid)))
            item = result.scalar_one_or_none()
            if item:
                _print_item(item)
            else:
                print(f"Item {fid} not found")

        # 再查所有 failed 的 item
        print(f"\n{'='*60}")
        print("All failed items:")
        result = await db.execute(
            select(Item).where(Item.feature_status == "failed").limit(10)
        )
        for item in result.scalars().all():
            _print_item(item)

def _print_item(item):
    print(f"\n{'='*60}")
    print(f"ID: {item.id}")
    print(f"Name: {item.name}")
    print(f"Category: {item.category}")
    print(f"Feature Status: {item.feature_status}")
    print(f"Feature Error: '{item.feature_error}'")
    print(f"Image URL: {item.image_url}")
    print(f"silhouette: {item.silhouette}")
    print(f"volume: {item.volume}")
    print(f"style_vector: {item.style_vector}")
    print(f"attributes: {item.attributes}")
    print(f"created_at: {item.created_at}")
    print(f"updated_at: {item.updated_at}")

asyncio.run(main())
