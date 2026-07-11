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


# V2 风格向量维度
_STYLE_KEYS = frozenset({
    "minimalist", "commute", "street", "sweet", "retro", "sporty",
    "luxury", "y2k", "japanese", "korean", "academic", "gorpcore",
})

_VALID_SILHOUETTES = frozenset({"H", "A", "X", "O", "T"})


def _clamp_silhouette(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    return v if v in _VALID_SILHOUETTES else None


def _clamp_scores_dict(value: Any, low: int = 1, high: int = 5) -> dict[str, int] | None:
    """将评分字典的值 clamp 到 [low, high] 范围。"""
    if not isinstance(value, dict):
        return None
    result: dict[str, int] = {}
    for k, v in value.items():
        if not isinstance(k, str):
            continue
        clamped = _clamp_int(v, low, high)
        if clamped is not None:
            result[k] = clamped
    return result or None


def _occasion_keys(scores: dict | None) -> list[str] | None:
    """从 occasion_scores 提取高分场景作为 occasion_tags fallback。"""
    if not isinstance(scores, dict) or not scores:
        return None
    # 取评分 >=3 的场景
    high = sorted(
        [(k, v) for k, v in scores.items() if isinstance(v, (int, float)) and v >= 3],
        key=lambda x: x[1],
        reverse=True,
    )
    return [k for k, _ in high[:5]] or None


def _apply_attributes(item: Item, attrs: dict[str, Any]) -> None:
    """V2: 写回四层属性到 Item 各字段。VLM 提取的 category 和 suggested_name 覆盖用户输入。"""
    item.attributes = attrs  # 完整 JSONB 保留

    # ---------- Layer1: 客观属性 ----------
    # category: VLM 提取的分类覆盖用户输入（用户可能未填或填错）
    vlm_category = attrs.get("category")
    if isinstance(vlm_category, str) and vlm_category.strip():
        cat = vlm_category.strip().lower()
        # 规范化中文分类为英文
        cat_map = {"上衣": "top", "裤子": "bottom", "裙子": "dress", "连衣裙": "dress",
                   "外套": "outerwear", "鞋履": "shoes", "鞋子": "shoes", "配饰": "accessory",
                   "套装": "set"}
        item.category = cat_map.get(cat, cat)

    # sub_category: 同样覆盖
    vlm_sub = attrs.get("subcategory")
    if isinstance(vlm_sub, str) and vlm_sub.strip():
        item.sub_category = vlm_sub.strip().lower()

    # suggested_name: VLM 生成的名称覆盖用户上传的名称
    suggested = attrs.get("suggested_name")
    if isinstance(suggested, str) and suggested.strip():
        item.name = suggested.strip()[:50]

    # is_full_outfit: 标记是否为完整套装/连衣裙（可单独推荐）
    is_full = attrs.get("is_full_outfit")
    if isinstance(is_full, bool):
        item.is_full_outfit = is_full
    elif item.category in ("dress", "set"):
        item.is_full_outfit = True
    else:
        item.is_full_outfit = False

    item.thickness = _clamp_int(attrs.get("thickness"), 1, 5)
    t_min, t_max = _parse_temperature(attrs.get("suitable_temperature"))
    item.suitable_temp_min = t_min
    item.suitable_temp_max = t_max
    item.color_hex_list = _hex_list(attrs.get("color_hex"))
    item.keywords = _str_list(attrs.get("keywords"))
    # occasion_tags: 优先从 suitable_occasions（旧字段兼容），否则从 occasion_scores 提取高分场景
    occ_tags = _str_list(attrs.get("suitable_occasions")) or _occasion_keys(attrs.get("occasion_scores"))
    item.occasion_tags = occ_tags

    # ---------- Layer2: 视觉属性 ----------
    item.silhouette = _clamp_silhouette(attrs.get("silhouette"))
    item.visual_weight = _clamp_int(attrs.get("visual_weight"), 1, 5)
    item.volume = _clamp_int(attrs.get("volume"), 1, 5)
    item.drape = _clamp_int(attrs.get("drape"), 1, 5)
    item.structure = _clamp_int(attrs.get("structure"), 1, 5)
    item.visual_focus = _str_list(attrs.get("visual_focus"), max_len=5)
    item.item_length = attrs.get("length") if isinstance(attrs.get("length"), str) else None

    # ---------- Layer3: 风格向量 ----------
    sv = attrs.get("style_vector")
    if isinstance(sv, dict):
        item.style_vector = {
            k: _clamp01(v) for k, v in sv.items()
            if isinstance(k, str) and k in _STYLE_KEYS
        }
    else:
        item.style_vector = None

    # ---------- Layer4: 搭配属性 ----------
    item.occasion_scores = _clamp_scores_dict(attrs.get("occasion_scores"), 1, 5)
    item.season_scores = _clamp_scores_dict(attrs.get("season_scores"), 1, 5)
    pp = attrs.get("pairing_preferences")
    if isinstance(pp, dict):
        item.pairing_preferences = {
            "best_match": _str_list(pp.get("best_match"), max_len=10) or [],
            "avoid": _str_list(pp.get("avoid"), max_len=10) or [],
        }
    else:
        item.pairing_preferences = None


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
