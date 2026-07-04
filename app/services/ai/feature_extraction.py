"""异步特征提取：结构化属性 + 视觉向量，同步写回 items 和 item_embeddings。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AIException
from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.item_embedding import ItemEmbedding
from app.services.ai.dashscope_client import dashscope_client
from app.services.ai.usage_logger import log_ai_usage

logger = logging.getLogger(__name__)


def _clamp01(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, min(1.0, v))


def _clamp_int(value: Any, low: int, high: int) -> int | None:
    try:
        v = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(low, min(high, v))


def _parse_temperature(value: Any) -> tuple[int | None, int | None]:
    if not isinstance(value, list) or len(value) < 2:
        return None, None
    try:
        low = int(round(float(value[0])))
        high = int(round(float(value[1])))
    except (TypeError, ValueError):
        return None, None
    if low > high:
        low, high = high, low
    return max(-30, min(50, low)), max(-30, min(50, high))


def _str_list(value: Any, max_len: int = 10) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for v in value:
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        result.append(s[:50])
        if len(result) >= max_len:
            break
    return result or None


def _hex_list(value: Any, max_len: int = 3) -> list[str] | None:
    if not isinstance(value, list):
        return None
    result: list[str] = []
    for v in value:
        if not isinstance(v, str):
            continue
        s = v.strip()
        if not s.startswith("#") or len(s) not in (4, 7):
            continue
        result.append(s.lower()[:10])
        if len(result) >= max_len:
            break
    return result or None


def _apply_attributes(item: Item, attrs: dict[str, Any]) -> None:
    """把 LLM JSON 写回 Item 各字段。原有 category 不覆盖以尊重用户选择。"""
    item.attributes = attrs

    style = attrs.get("style_attributes") or {}
    item.formality = _clamp01(style.get("formality"))
    item.femininity = _clamp01(style.get("femininity"))
    item.athletic = _clamp01(style.get("athletic"))
    item.vintage = _clamp01(style.get("vintage"))

    item.thickness = _clamp_int(attrs.get("thickness"), 1, 5)

    t_min, t_max = _parse_temperature(attrs.get("suitable_temperature"))
    item.suitable_temp_min = t_min
    item.suitable_temp_max = t_max

    item.occasion_tags = _str_list(attrs.get("suitable_occasions"))
    item.color_hex_list = _hex_list(attrs.get("color_hex"))
    item.keywords = _str_list(attrs.get("keywords"))


def _is_clothing(attrs: dict[str, Any]) -> tuple[bool, str | None]:
    """根据 LLM 返回的 is_clothing 字段判断是否为有效服装。"""
    # 新 schema：显式声明
    is_clothing = attrs.get("is_clothing")
    if isinstance(is_clothing, bool):
        if not is_clothing:
            note = attrs.get("validation_note")
            if isinstance(note, str) and note.strip():
                return False, note.strip()[:100]
            return False, "未检测到服装，请上传平铺或悬挂的衣物照片"
        return True, None

    # 兼容旧数据：没有 is_clothing 字段时，根据 category 兜底判断
    category = attrs.get("category")
    allowed = {"上衣", "裤子", "裙子", "外套", "鞋履", "配饰", "top", "bottom", "dress", "outer", "shoes", "acc"}
    if isinstance(category, str) and category in allowed:
        return True, None

    return False, "未检测到服装，请上传平铺或悬挂的衣物照片"


def _safe_attr(attrs: dict[str, Any], key: str, default: Any = None) -> Any:
    """安全取值，忽略 null/None。"""
    value = attrs.get(key, default)
    return default if value is None else value


async def _upsert_embedding(
    db: AsyncSession, user_id: UUID, item_id: UUID, embedding: list[float]
) -> None:
    stmt = (
        pg_insert(ItemEmbedding)
        .values(user_id=user_id, item_id=item_id, embedding=embedding)
        .on_conflict_do_update(
            index_elements=["item_id"],
            set_={"embedding": embedding, "user_id": user_id},
        )
    )
    await db.execute(stmt)


async def extract_and_store(db: AsyncSession, item_id: UUID) -> None:
    """核心：并发调用 MLLM + Embedding，写回 items / item_embeddings。"""
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        logger.warning("feature_extraction: item %s not found", item_id)
        return

    if not item.image_url:
        item.feature_status = "failed"
        item.feature_error = "no image_url"
        await db.commit()
        return

    item.feature_status = "processing"
    item.feature_error = None
    await db.commit()

    try:
        attrs_task = dashscope_client.extract_attributes(item.image_url, item.category)
        emb_task = dashscope_client.embed_image(item.image_url)
        attrs, embedding = await asyncio.gather(attrs_task, emb_task)
    except AIException as exc:
        logger.warning("feature_extraction failed for %s: %s", item_id, exc)
        # 重新拉取，避免会话内 item 已过期
        result = await db.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()
        if item is not None:
            item.feature_status = "failed"
            item.feature_error = str(exc)[:500]
            await db.commit()
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("feature_extraction unexpected error for %s", item_id)
        result = await db.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()
        if item is not None:
            item.feature_status = "failed"
            item.feature_error = str(exc)[:500]
            await db.commit()
        return

    # 写回结构化 + 向量（同事务）
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        return

    # 校验是否为有效服装
    is_valid, error_note = _is_clothing(attrs)
    if not is_valid:
        item.feature_status = "failed"
        item.feature_error = error_note
        await db.commit()
        logger.warning("feature_extraction not clothing item=%s: %s", item_id, error_note)
        return

    _apply_attributes(item, attrs)
    item.feature_status = "success"
    item.feature_error = None
    await _upsert_embedding(db, item.user_id, item.id, embedding)
    await db.commit()
    logger.info("feature_extraction success item=%s", item_id)

    # 记录 AI 调用（不计费，仅作后续计费依据）
    await log_ai_usage(
        db,
        user_id=item.user_id,
        action="attribute_extract",
        model=settings.ai_attribute_model,
        metadata={"item_id": str(item.id)},
    )
    await log_ai_usage(
        db,
        user_id=item.user_id,
        action="embedding",
        model=settings.ai_embedding_model,
        metadata={"item_id": str(item.id), "dim": len(embedding)},
    )


async def enqueue_extraction(item_id: UUID) -> None:
    """FastAPI BackgroundTasks 入口：使用独立 session 执行，避免与请求会话冲突。"""

    async def _run() -> None:
        async with AsyncSessionLocal() as session:
            try:
                await extract_and_store(session, item_id)
            except Exception:  # noqa: BLE001
                logger.exception("enqueue_extraction background error item=%s", item_id)

    # 直接 await 以便 BackgroundTasks 顺序执行；也可以 create_task 后立即返回。
    await _run()
