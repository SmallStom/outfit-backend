"""批量导入服务：并发处理多张图片，衣物提取 + COS 保存 + Item 创建 + 任务管理。"""
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AIException
from app.db.session import AsyncSessionLocal
from app.models.import_batch import ImportBatch
from app.models.item import Item
from app.services.cos import upload_bytes_to_cos
from app.services.garment_extract_service import extract_and_validate_garment

logger = logging.getLogger(__name__)


async def create_batch(db: AsyncSession, user_id: UUID, total_count: int) -> ImportBatch:
    """创建批量导入记录。"""
    batch = ImportBatch(
        user_id=user_id,
        status="processing",
        total_count=total_count,
        success_count=0,
        failed_count=0,
    )
    db.add(batch)
    await db.commit()
    await db.refresh(batch)
    return batch


async def _create_item(
    user_id: UUID,
    batch_id: UUID,
    image_url: str,
    feature_status: str,
    feature_error: str | None = None,
) -> Item:
    """在独立 session 中创建 Item。"""
    async with AsyncSessionLocal() as session:
        item = Item(
            user_id=user_id,
            batch_id=batch_id,
            name="快速导入",
            category="unknown",
            image_url=image_url,
            feature_status=feature_status,
            feature_error=feature_error,
            wear_count=0,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item


async def process_single_image(
    user_id: UUID,
    batch_id: UUID,
    content: bytes,
    ext: str,
    content_type: str,
) -> dict:
    """处理单张图片的完整流程（在并发信号量内执行）。

    返回 {status, item_id, image_url, error}
    """
    # 1. 上传原图到 COS
    try:
        original_url = await upload_bytes_to_cos(content, content_type, ext, folder="items")
    except Exception as exc:
        logger.error("批量导入 COS 上传原图失败: %s", exc)
        return {"status": "failed", "error": "图片上传失败，请重试"}

    # 2. 衣物提取 + 验证
    try:
        garment_data, garment_ct = await extract_and_validate_garment(original_url)
    except AIException as exc:
        # 提取失败 -> 创建 failed Item 保留原图
        logger.warning("批量导入衣物提取失败: %s", exc)
        item = await _create_item(
            user_id, batch_id, original_url,
            feature_status="failed",
            feature_error=str(exc)[:500],
        )
        return {"status": "failed", "error": str(exc), "item_id": item.id}
    except Exception as exc:
        logger.exception("批量导入衣物提取异常")
        item = await _create_item(
            user_id, batch_id, original_url,
            feature_status="failed",
            feature_error=str(exc)[:500],
        )
        return {"status": "failed", "error": "衣物提取异常，请重试", "item_id": item.id}

    # 3. 上传提取后的衣物图到 COS
    try:
        garment_url = await upload_bytes_to_cos(garment_data, garment_ct, "png", folder="items")
    except Exception as exc:
        logger.error("批量导入 COS 上传提取图失败: %s", exc)
        item = await _create_item(
            user_id, batch_id, original_url,
            feature_status="failed",
            feature_error=f"提取图保存失败: {str(exc)[:200]}",
        )
        return {"status": "failed", "error": "提取图保存失败", "item_id": item.id}

    # 4. 创建 Item
    item = await _create_item(
        user_id, batch_id, garment_url,
        feature_status="processing",
    )
    logger.info("批量导入成功 item=%s image=%s", item.id, garment_url)
    return {"status": "success", "item_id": item.id, "image_url": garment_url}


async def batch_import(
    db: AsyncSession,
    user_id: UUID,
    files: list[tuple[bytes, str, str]],
    background_tasks=None,
) -> tuple[ImportBatch, list[dict]]:
    """批量导入主入口。

    files: [(content, ext, content_type), ...]
    返回 (ImportBatch, results) 其中 results 是每张图片的处理结果。
    """
    # 1. 创建批量记录
    batch = await create_batch(db, user_id, total_count=len(files))

    # 2. 并发处理
    sem = asyncio.Semaphore(settings.batch_import_concurrency)

    async def _process_wrapper(content: bytes, ext: str, content_type: str) -> dict:
        async with sem:
            return await process_single_image(user_id, batch.id, content, ext, content_type)

    results = await asyncio.gather(
        *[_process_wrapper(c, e, ct) for c, e, ct in files]
    )

    # 3. 更新 batch 状态
    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = len(results) - success_count

    # 重新获取 batch（session 可能已过期）
    batch_result = await db.execute(select(ImportBatch).where(ImportBatch.id == batch.id))
    batch = batch_result.scalar_one()
    batch.success_count = success_count
    batch.failed_count = failed_count
    batch.status = "completed" if failed_count == 0 else "partially_completed"
    await db.commit()
    await db.refresh(batch)

    # 4. 为成功的 item 添加后台属性提取任务
    if background_tasks:
        from app.services.ai.feature_extraction import enqueue_extraction
        for result in results:
            if result["status"] == "success" and result.get("item_id"):
                background_tasks.add_task(enqueue_extraction, result["item_id"])

    return batch, list(results)


async def get_batch_status(
    db: AsyncSession, user_id: UUID, batch_id: UUID
) -> dict:
    """查询批量任务状态 + 关联的 items 列表。"""
    result = await db.execute(
        select(ImportBatch).where(
            ImportBatch.id == batch_id,
            ImportBatch.user_id == user_id,
        )
    )
    batch = result.scalar_one_or_none()
    if batch is None:
        from app.core.exceptions import NotFoundException
        raise NotFoundException("批量导入任务不存在")

    items_result = await db.execute(
        select(Item).where(
            Item.batch_id == batch_id,
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        ).order_by(Item.created_at.asc())
    )
    items = list(items_result.scalars().all())

    return {
        "batch_id": batch.id,
        "status": batch.status,
        "total": batch.total_count,
        "success": batch.success_count,
        "failed": batch.failed_count,
        "created_at": batch.created_at,
        "items": items,
    }
