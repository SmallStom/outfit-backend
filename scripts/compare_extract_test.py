"""衣物提取对比测试：同一张图片分别走 image_edit 和 aliyun_parsing 两种方式，
逐步打印耗时、输入输出，并保存中间图片到本地方便排查。

用法: python -m scripts.compare_extract_test
"""
from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import sys
import time
from pathlib import Path

import httpx

# Windows 终端编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
os.environ["DEBUG"] = "false"

from sqlalchemy import select

from app.core.config import settings
settings.debug = False
from app.db.session import AsyncSessionLocal, engine as _engine
_engine.echo = False

from app.models.import_batch import ImportBatch
from app.models.item import Item
from app.models.user import User
from app.services.ai.feature_extraction import extract_and_store
from app.services.cos import upload_bytes_to_cos
from app.services.garment_extract_service import (
    _flatten_on_white_bg,
    _download_image_direct,
    category_to_clothes_type,
    extract_and_validate_garment,
    extract_garment_aliyun_parsing,
    validate_garment_image,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("compare_extract_test")

# ==================== 配置 ==================== #

SHOP_DATA_DIR = Path(__file__).parent / "data" / "50shop"
STOM_OPENID = "stom"
OUTPUT_DIR = Path(__file__).parent / "data" / "compare_extract_output"

# 测试图片（只取 1 张，方便对比）
TEST_IMAGE = "images/img_0093625.jpg"


# ==================== 工具函数 ==================== #

def _load_image(path: Path) -> tuple[bytes, str, str]:
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "image/jpeg"
    ext = "jpg" if "jpeg" in mime_type else mime_type.split("/")[1]
    with open(path, "rb") as f:
        return f.read(), ext, mime_type


def _save_local(data: bytes, name: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUTPUT_DIR / name
    p.write_bytes(data)
    return p


async def _download_to_local(url: str, name: str) -> Path:
    data, _ = await _download_image_direct(url)
    return _save_local(data, name)


async def _get_or_create_user(db) -> User:
    result = await db.execute(select(User).where(User.openid == STOM_OPENID))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(openid=STOM_OPENID, nickname="stom", gender="female", is_new_user=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


async def _create_item(user_id, batch_id, image_url, feature_status="processing") -> Item:
    async with AsyncSessionLocal() as s:
        item = Item(
            user_id=user_id, batch_id=batch_id, name="对比测试",
            category="unknown", image_url=image_url,
            feature_status=feature_status, wear_count=0,
        )
        s.add(item)
        await s.commit()
        await s.refresh(item)
        return item


async def _update_item_image(item_id, image_url):
    from uuid import UUID
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()
        if item:
            item.image_url = image_url
            await s.commit()


def _fmt_size(data: bytes) -> str:
    return f"{len(data) / 1024:.1f}KB"


def _print_step(step: int, name: str, elapsed: float, detail: str = ""):
    msg = f"  Step {step}: {name:<35s} [{elapsed:.1f}s]"
    if detail:
        msg += f"  {detail}"
    print(msg)


# ==================== 方法一：image_edit ==================== #

async def test_image_edit(user_id, batch_id, original_url: str, image_name: str) -> dict:
    print(f"\n{'=' * 70}")
    print(f"  方法一: image_edit (GPT images/edits)")
    print(f"{'=' * 70}")
    timings = {}

    # Step 1: 衣物提取
    t0 = time.time()
    print(f"\n  输入: {original_url}")
    try:
        garment_data, garment_ct = await extract_and_validate_garment(original_url)
    except Exception as exc:
        elapsed = time.time() - t0
        _print_step(1, "images/edits 提取+验证", elapsed, f"FAILED: {exc}")
        return {"method": "image_edit", "status": "failed", "error": str(exc), "timings": timings}
    timings["extract"] = time.time() - t0
    _print_step(1, "images/edits 提取+验证", timings["extract"],
                f"size={_fmt_size(garment_data)}, ct={garment_ct}")

    # 保存提取图到本地
    local_path = _save_local(garment_data, f"{image_name}_edit_extracted.png")
    print(f"         本地保存: {local_path}")

    # Step 2: 上传到 COS
    t0 = time.time()
    garment_url = await upload_bytes_to_cos(garment_data, garment_ct, "png", folder="items")
    timings["cos_upload"] = time.time() - t0
    _print_step(2, "上传提取图到 COS", timings["cos_upload"], garment_url[:80])

    # Step 3: 创建 Item
    t0 = time.time()
    item = await _create_item(user_id, batch_id, garment_url)
    timings["create_item"] = time.time() - t0
    _print_step(3, "创建 Item", timings["create_item"], f"id={item.id}")

    # Step 4: 属性提取
    t0 = time.time()
    async with AsyncSessionLocal() as s:
        await extract_and_store(s, item.id)
    timings["attr_extract"] = time.time() - t0
    _print_step(4, "属性提取 (extract_and_store)", timings["attr_extract"])

    # 读取属性
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Item).where(Item.id == item.id))
        updated = result.scalar_one_or_none()
    category = updated.category if updated else "?"
    feature_status = updated.feature_status if updated else "?"
    print(f"         category={category}, feature_status={feature_status}")

    total = sum(timings.values())
    print(f"\n  总耗时: {total:.1f}s")
    return {
        "method": "image_edit", "status": "success", "item_id": item.id,
        "garment_url": garment_url, "category": category,
        "timings": timings, "total": total,
    }


# ==================== 方法二：aliyun_parsing ==================== #

async def test_aliyun_parsing(user_id, batch_id, original_url: str, image_name: str) -> dict:
    print(f"\n{'=' * 70}")
    print(f"  方法二: aliyun_parsing (aitryon-parsing-v1)")
    print(f"{'=' * 70}")
    timings = {}

    # Step 1: 创建 Item（用原图）
    t0 = time.time()
    item = await _create_item(user_id, batch_id, original_url)
    timings["create_item"] = time.time() - t0
    _print_step(1, "创建 Item (原图)", timings["create_item"], f"id={item.id}")

    # Step 2: 属性提取
    t0 = time.time()
    async with AsyncSessionLocal() as s:
        await extract_and_store(s, item.id)
    timings["attr_extract"] = time.time() - t0
    _print_step(2, "属性提取 (extract_and_store)", timings["attr_extract"])

    # 读取 category
    async with AsyncSessionLocal() as s:
        result = await s.execute(select(Item).where(Item.id == item.id))
        updated = result.scalar_one_or_none()
    category = updated.category if updated else "?"
    feature_status = updated.feature_status if updated else "?"
    print(f"         category={category}, feature_status={feature_status}")

    if feature_status != "success":
        total = sum(timings.values())
        print(f"\n  总耗时: {total:.1f}s (属性提取失败，跳过分割)")
        return {"method": "aliyun_parsing", "status": "failed",
                "error": "属性提取失败", "timings": timings, "total": total}

    # Step 3: category -> clothes_type
    clothes_type = category_to_clothes_type(category)
    if clothes_type is None:
        total = sum(timings.values())
        print(f"\n  分类 {category} 不支持分割，保留原图")
        return {"method": "aliyun_parsing", "status": "success",
                "item_id": item.id, "garment_url": original_url,
                "category": category, "timings": timings, "total": total,
                "note": f"分类 {category} 不支持，保留原图"}

    print(f"         clothes_type={clothes_type}")

    # Step 4: aitryon-parsing-v1 分割
    t0 = time.time()
    try:
        garment_data, garment_ct = await extract_garment_aliyun_parsing(original_url, clothes_type)
    except Exception as exc:
        elapsed = time.time() - t0
        _print_step(4, "aitryon-parsing 分割", elapsed, f"FAILED: {exc}")
        total = sum(timings.values()) + elapsed
        return {"method": "aliyun_parsing", "status": "failed",
                "error": str(exc), "timings": timings, "total": total}
    timings["parsing"] = time.time() - t0
    _print_step(4, "aitryon-parsing 分割", timings["parsing"],
                f"size={_fmt_size(garment_data)}, ct={garment_ct}")

    # 保存提取图到本地
    local_path = _save_local(garment_data, f"{image_name}_parsing_extracted.png")
    print(f"         本地保存: {local_path}")

    # Step 5: 上传到 COS
    t0 = time.time()
    ext = "png" if "png" in garment_ct else "jpg"
    garment_url = await upload_bytes_to_cos(garment_data, garment_ct, ext, folder="items")
    timings["cos_upload"] = time.time() - t0
    _print_step(5, "上传分割图到 COS", timings["cos_upload"], garment_url[:80])

    # Step 6: 更新 Item.image_url
    t0 = time.time()
    await _update_item_image(item.id, garment_url)
    timings["update_item"] = time.time() - t0
    _print_step(6, "更新 Item.image_url", timings["update_item"])

    total = sum(timings.values())
    print(f"\n  总耗时: {total:.1f}s")
    return {
        "method": "aliyun_parsing", "status": "success", "item_id": item.id,
        "garment_url": garment_url, "category": category,
        "timings": timings, "total": total,
    }


# ==================== 主流程 ==================== #

async def main():
    print("=" * 70)
    print("  衣物提取对比测试")
    print("=" * 70)

    # 验证配置
    if not settings.image_edit_api_key:
        print("  [跳过] IMAGE_EDIT_API_KEY 未配置")
    if not settings.tryon_segment_api_key:
        print("  [警告] TRYON_SEGMENT_API_KEY 未配置，aliyun_parsing 方式将失败")
    if not settings.ai_api_key:
        print("  [错误] AI_API_KEY 未配置，属性提取将失败")
        return

    image_path = SHOP_DATA_DIR / TEST_IMAGE
    if not image_path.exists():
        print(f"  [错误] 测试图片不存在: {image_path}")
        return

    image_name = image_path.stem
    content, ext, content_type = _load_image(image_path)
    print(f"\n  测试图片: {TEST_IMAGE}")
    print(f"  大小: {_fmt_size(content)}, 类型: {content_type}")

    # 保存原图到输出目录
    _save_local(content, f"{image_name}_original.{ext}")
    print(f"  原图已保存到: {OUTPUT_DIR / f'{image_name}_original.{ext}'}")

    async with AsyncSessionLocal() as db:
        user = await _get_or_create_user(db)

        # 创建 batch
        batch = ImportBatch(user_id=user.id, status="processing", total_count=1)
        db.add(batch)
        await db.commit()
        await db.refresh(batch)

        # 上传原图到 COS（两种方式共用）
        t0 = time.time()
        original_url = await upload_bytes_to_cos(content, content_type, ext, folder="items")
        cos_time = time.time() - t0
        print(f"\n  原图上传 COS: [{cos_time:.1f}s] {original_url[:80]}")

        # 方法一：image_edit
        result1 = await test_image_edit(user.id, batch.id, original_url, image_name)

        # 方法二：aliyun_parsing
        result2 = await test_aliyun_parsing(user.id, batch.id, original_url, image_name)

    # ==================== 对比汇总 ==================== #
    print(f"\n{'=' * 70}")
    print(f"  对比汇总")
    print(f"{'=' * 70}")
    print(f"  {'指标':<25s} {'image_edit':<25s} {'aliyun_parsing':<25s}")
    print(f"  {'-' * 75}")

    r1, r2 = result1, result2
    print(f"  {'状态':<25s} {r1['status']:<25s} {r2['status']:<25s}")
    print(f"  {'总耗时':<24s} {r1.get('total', 0):.1f}s{'':<20s} {r2.get('total', 0):.1f}s")

    if r1["status"] == "success" and r2["status"] == "success":
        print(f"  {'category':<25s} {r1.get('category', '?'):<25s} {r2.get('category', '?'):<25s}")

        # 下载两种方式的提取图到本地
        for label, result in [("edit", r1), ("parsing", r2)]:
            url = result.get("garment_url", "")
            if url and url != original_url:
                try:
                    p = await _download_to_local(url, f"{image_name}_{label}_final.png")
                    print(f"  {'最终图(本地)':<24s} {label + ': ' + str(p.name):<50s}")
                except Exception:
                    pass

    # 详细耗时对比
    print(f"\n  各步骤耗时明细:")
    all_steps = sorted(set(list(r1.get("timings", {}).keys()) + list(r2.get("timings", {}).keys())))
    print(f"  {'步骤':<25s} {'image_edit':<15s} {'aliyun_parsing':<15s}")
    print(f"  {'-' * 55}")
    for step in all_steps:
        t1 = r1.get("timings", {}).get(step, 0)
        t2 = r2.get("timings", {}).get(step, 0)
        print(f"  {step:<25s} {t1:>6.1f}s{'':>8s} {t2:>6.1f}s")

    if r1.get("error"):
        print(f"\n  image_edit 错误: {r1['error']}")
    if r2.get("error"):
        print(f"\n  aliyun_parsing 错误: {r2['error']}")
    if r2.get("note"):
        print(f"\n  aliyun_parsing 备注: {r2['note']}")

    print(f"\n  本地输出目录: {OUTPUT_DIR}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    asyncio.run(main())
