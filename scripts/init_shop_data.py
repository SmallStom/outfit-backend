"""使用 50shop 数据集初始化外部商品池。

用法：
    python scripts/init_shop_data.py
    python scripts/init_shop_data.py --skip-cleanup
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.outfit import Outfit
from app.models.shop_item import ShopItem
from app.models.tryon_preset import TryonPreset
from app.models.user import User
from app.models.wear_history import WearHistory
from app.services.cos import is_cos_configured, upload_bytes_to_cos

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "50shop")
ITEMS_JSON = os.path.join(DATA_DIR, "items.json")

TARGET_OPENID = "dev-user"


def _detect_image_format(content: bytes) -> str | None:
    if len(content) < 12:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


async def _upload_local_image(local_path: str) -> str | None:
    """把本地图片上传到 COS，返回公网 URL；失败返回 None。"""
    if not is_cos_configured():
        return None
    if not os.path.exists(local_path):
        return None
    try:
        with open(local_path, "rb") as f:
            data = f.read()
        ext = _detect_image_format(data)
        if not ext:
            return None
        content_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
        return await upload_bytes_to_cos(data, content_type, ext, folder="shop")
    except Exception as exc:  # noqa: BLE001
        print(f"upload failed {local_path}: {exc}")
        return None


async def cleanup_dev_user(db: AsyncSession) -> None:
    """清理 dev-user 的旧 mock 衣橱数据与搭配。"""
    result = await db.execute(select(User).where(User.openid == TARGET_OPENID))
    user = result.scalar_one_or_none()
    if user is None:
        print(f"dev user {TARGET_OPENID} not found, skip cleanup")
        return

    user_id = user.id
    # 删除 outfits 会级联删除 outfit_items / outfit_feedbacks
    result = await db.execute(select(Outfit).where(Outfit.user_id == user_id))
    for outfit in result.scalars().all():
        await db.delete(outfit)

    result = await db.execute(select(Item).where(Item.user_id == user_id))
    for item in result.scalars().all():
        await db.delete(item)

    result = await db.execute(select(TryonPreset).where(TryonPreset.user_id == user_id))
    for preset in result.scalars().all():
        await db.delete(preset)

    result = await db.execute(select(WearHistory).where(WearHistory.user_id == user_id))
    for record in result.scalars().all():
        await db.delete(record)

    await db.flush()
    print(f"cleaned up old data for dev user {user_id}")


async def import_shop_items(db: AsyncSession) -> int:
    """导入 50shop 商品，返回导入数量。"""
    with open(ITEMS_JSON, "r", encoding="utf-8") as f:
        raw_items = json.load(f)

    # 清空旧 shop_items
    await db.execute(text("DELETE FROM shop_items"))
    await db.flush()
    print("cleared existing shop_items")

    count = 0
    for raw in raw_items:
        local_path = raw.get("localImagePath")
        image_url = raw.get("imageUrl", "")
        if local_path:
            local_full = os.path.normpath(os.path.join(DATA_DIR, local_path.replace("\\", "/")))
            uploaded = await _upload_local_image(local_full)
            if uploaded:
                image_url = uploaded

        shop_item = ShopItem(
            name=raw["name"],
            category=raw["category"],
            sub_category=raw.get("subCategory"),
            image_url=image_url,
            thumbnail_url=None,
            image_color=None,
            price=raw.get("price"),
            brand=raw.get("brand"),
            material=raw.get("material"),
            color=raw.get("color"),
            color_hex=raw.get("colorHex"),
            season=raw.get("season"),
            tags=raw.get("tags", []),
            description=raw.get("description", ""),
            source_url=raw.get("sourceUrl", ""),
            is_enabled=True,
        )
        db.add(shop_item)
        count += 1

    await db.flush()
    print(f"imported {count} shop items")
    return count


async def main(skip_cleanup: bool = False) -> None:
    async with AsyncSessionLocal() as db:
        if not skip_cleanup:
            await cleanup_dev_user(db)
        await import_shop_items(db)
        await db.commit()
        print("shop data initialized successfully")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cleanup", action="store_true", help="跳过清理 dev-user 旧数据")
    args = parser.parse_args()
    asyncio.run(main(skip_cleanup=args.skip_cleanup))
