"""批量导入测试：2 张图片走完整流程（HighwayAPI 衣物提取 + DashScope 属性提取）。

流程：
1. 创建/获取 stom 用户
2. 选取 2 张本地衣物图片
3. 创建 ImportBatch 记录
4. 对每张图片：
   a. 上传原图到 COS
   b. HighwayAPI 提取衣物（纯白背景）
   c. Pillow 验证提取结果
   d. 保存提取图到 COS
   e. 创建 Item（batch_id 关联）
5. 对成功的 item 调用 extract_and_store()（DashScope 属性提取 + embedding）
6. 打印结果

用法: python -m scripts.quick_import_test
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import sys
import time
from pathlib import Path
from uuid import UUID

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
from app.services.batch_import_service import process_single_image

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("quick_import_test")

# ==================== 配置 ==================== #

SHOP_DATA_DIR = Path(__file__).parent / "data" / "50shop"
STOM_OPENID = "stom"

# 选取 2 张测试图片
TEST_IMAGE_FILES = [
    "images/img_0093625.jpg",
    "images/img_0185318.jpg",
]


# ==================== 工具函数 ==================== #

def _load_image(path: Path) -> tuple[bytes, str, str]:
    """读取本地图片，返回 (data, ext, content_type)。"""
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "image/jpeg"
    ext = mime_type.split("/")[1]
    if ext == "jpeg":
        ext = "jpg"
    with open(path, "rb") as f:
        return f.read(), ext, f"image/{mime_type.split('/')[1]}"


async def _get_or_create_user(db) -> User:
    """获取或创建 stom 用户。"""
    result = await db.execute(select(User).where(User.openid == STOM_OPENID))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(openid=STOM_OPENID, nickname="stom", gender="female", is_new_user=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("已创建用户 stom (id=%s)", user.id)
    else:
        logger.info("用户 stom 已存在 (id=%s)", user.id)
    return user


# ==================== 主流程 ==================== #

async def main():
    logger.info("=" * 60)
    logger.info("批量导入测试开始")
    logger.info("=" * 60)

    # 验证配置
    if not settings.highway_api_key:
        logger.error("HIGHWAY_API_KEY 未配置，无法测试衣物提取")
        return
    if not settings.ai_api_key:
        logger.error("AI_API_KEY 未配置，无法测试属性提取")
        return

    async with AsyncSessionLocal() as db:
        # 1. 获取/创建用户
        user = await _get_or_create_user(db)

        # 2. 创建 ImportBatch
        batch = ImportBatch(
            user_id=user.id,
            status="processing",
            total_count=len(TEST_IMAGE_FILES),
        )
        db.add(batch)
        await db.commit()
        await db.refresh(batch)
        logger.info("创建 ImportBatch (id=%s, total=%d)", batch.id, batch.total_count)

        # 3. 并发处理图片
        sem = asyncio.Semaphore(settings.batch_import_concurrency)

        async def _process(image_rel_path: str, index: int) -> dict:
            async with sem:
                image_path = SHOP_DATA_DIR / image_rel_path
                if not image_path.exists():
                    logger.error("[%d] 图片不存在: %s", index, image_path)
                    return {"status": "failed", "error": "图片不存在"}

                name = image_path.stem
                logger.info("[%d] 开始处理: %s", index, name)
                t0 = time.time()

                content, ext, content_type = _load_image(image_path)

                result = await process_single_image(
                    user_id=user.id,
                    batch_id=batch.id,
                    content=content,
                    ext=ext,
                    content_type=content_type,
                )

                elapsed = time.time() - t0
                logger.info(
                    "[%d] 完成: %s | status=%s | %.1fs",
                    index, name, result["status"], elapsed,
                )
                return result

        results = await asyncio.gather(
            *[_process(path, i) for i, path in enumerate(TEST_IMAGE_FILES, 1)]
        )

        # 4. 更新 batch 状态
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = len(results) - success_count

        batch_result = await db.execute(select(ImportBatch).where(ImportBatch.id == batch.id))
        batch = batch_result.scalar_one()
        batch.success_count = success_count
        batch.failed_count = failed_count
        batch.status = "completed" if failed_count == 0 else "partially_completed"
        await db.commit()
        await db.refresh(batch)

        logger.info(
            "ImportBatch 完成: status=%s, success=%d, failed=%d",
            batch.status, batch.success_count, batch.failed_count,
        )

        # 5. 对成功的 item 调用属性提取
        success_items: list[UUID] = [
            r["item_id"] for r in results if r["status"] == "success" and r.get("item_id")
        ]

        if success_items:
            logger.info("开始 DashScope 属性提取（%d 件）...", len(success_items))
            for item_id in success_items:
                t0 = time.time()
                logger.info("属性提取 item=%s ...", item_id)
                try:
                    async with AsyncSessionLocal() as extract_db:
                        await extract_and_store(extract_db, item_id)
                    elapsed = time.time() - t0
                    logger.info("属性提取完成 item=%s | %.1fs", item_id, elapsed)
                except Exception as exc:
                    logger.error("属性提取失败 item=%s: %s", item_id, exc)

        # 6. 打印结果
        print(f"\n{'=' * 80}")
        print(f"  批量导入测试结果")
        print(f"{'=' * 80}")
        print(f"  Batch ID: {batch.id}")
        print(f"  状态: {batch.status}")
        print(f"  总计: {batch.total_count} | 成功: {batch.success_count} | 失败: {batch.failed_count}")
        print()

        for i, result in enumerate(results, 1):
            status_icon = "OK" if result["status"] == "success" else "FAIL"
            print(f"  #{i} [{status_icon}] {TEST_IMAGE_FILES[i-1]}")
            if result["status"] == "success":
                print(f"       Item ID: {result.get('item_id')}")
                print(f"       提取图 URL: {result.get('image_url')}")

                # 查询 item 属性
                if result.get("item_id"):
                    item_result = await db.execute(
                        select(Item).where(Item.id == result["item_id"])
                    )
                    item = item_result.scalar_one_or_none()
                    if item:
                        print(f"       名称: {item.name}")
                        print(f"       分类: {item.category}")
                        print(f"       特征状态: {item.feature_status}")
                        if item.feature_error:
                            print(f"       错误: {item.feature_error}")
                        if item.style_vector:
                            top_styles = sorted(
                                item.style_vector.items(),
                                key=lambda x: x[1],
                                reverse=True,
                            )[:3]
                            style_str = ", ".join(f"{k}={v:.1f}" for k, v in top_styles)
                            print(f"       风格: {style_str}")
                        if item.silhouette:
                            print(f"       廓形: {item.silhouette}")
                        if item.suitable_temp_min is not None:
                            print(f"       温度: {item.suitable_temp_min}~{item.suitable_temp_max}°C")
            else:
                print(f"       错误: {result.get('error')}")
            print()

    logger.info("=" * 60)
    logger.info("批量导入测试完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
