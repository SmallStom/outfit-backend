"""推荐引擎主流程：候选筛选 → 组合打分 → Top10 → LLM 精排 → 写库返回。

进程内 (user_id, temp_bucket) TTL 缓存，避免同温度短时间内反复调用 LLM。
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import Item
from app.models.item_embedding import ItemEmbedding
from app.models.outfit import Outfit, OutfitItem
from app.models.outfit_feedback import OutfitFeedback
from app.services.ai.dashscope_client import dashscope_client, sanitize_prompt_text
from app.services.ai.usage_logger import log_ai_usage
from app.services.ai.weather_service import WeatherResult
from app.services.reco import scorer

logger = logging.getLogger(__name__)


class InsufficientCandidatesError(Exception):
    """候选池不足（如缺少上衣/下装）时抛出，携带友好提示。"""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_MAX_SIZE = 1000


def _cleanup_cache() -> None:
    """主动清理过期条目；若仍超过上限，删除最老的 20%。"""
    now = time.time()
    ttl = settings.reco_cache_ttl_minutes * 60
    expired = [k for k, (ts, _) in _cache.items() if (now - ts) > ttl]
    for k in expired:
        _cache.pop(k, None)
    if len(_cache) > _CACHE_MAX_SIZE:
        # 按时间戳升序，删除最老的 20%
        sorted_items = sorted(_cache.items(), key=lambda x: x[1][0])
        to_remove = int(_CACHE_MAX_SIZE * 0.2)
        for k, _ in sorted_items[:to_remove]:
            _cache.pop(k, None)


def _cache_key(user_id: UUID, temp: float, weather_text: str) -> str:
    bucket = round(temp / 3.0) * 3
    return f"{user_id}:{bucket}:{weather_text[:4]}"


def _get_cached(key: str) -> list[dict[str, Any]] | None:
    entry = _cache.get(key)
    if not entry:
        return None
    ts, payload = entry
    if (time.time() - ts) > settings.reco_cache_ttl_minutes * 60:
        _cache.pop(key, None)
        return None
    return payload


def _set_cached(key: str, payload: list[dict[str, Any]]) -> None:
    _cleanup_cache()
    _cache[key] = (time.time(), payload)


async def _load_feedback_map(db: AsyncSession, user_id: UUID) -> dict[str, int]:
    """按 item_id 聚合 (like - dislike)。"""
    stmt = (
        select(
            OutfitFeedback.item_id,
            OutfitFeedback.action,
            func.count().label("cnt"),
        )
        .where(OutfitFeedback.user_id == user_id, OutfitFeedback.item_id.is_not(None))
        .group_by(OutfitFeedback.item_id, OutfitFeedback.action)
    )
    result = await db.execute(stmt)
    fmap: dict[str, int] = {}
    for item_id, action, cnt in result.all():
        key = str(item_id)
        fmap[key] = fmap.get(key, 0) + (cnt if action == "like" else -cnt)
    return fmap


async def _load_disliked_items(
    db: AsyncSession,
    user_id: UUID,
    days: int = 30,
    min_count: int = 2,
) -> set[UUID]:
    """返回最近 N 天内被 dislike 达到 min_count 次的单品 ID（软屏蔽集合）。"""
    from datetime import timedelta

    from app.core.timezone import now_bj

    since = now_bj() - timedelta(days=days)
    stmt = (
        select(OutfitFeedback.item_id)
        .where(
            OutfitFeedback.user_id == user_id,
            OutfitFeedback.action == "dislike",
            OutfitFeedback.item_id.is_not(None),
            OutfitFeedback.created_at >= since,
        )
        .group_by(OutfitFeedback.item_id)
        .having(func.count() >= min_count)
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.all()}


async def _load_candidates(
    db: AsyncSession, user_id: UUID, temp: float, weather_text: str
) -> tuple[list[Item], list[Item], dict[UUID, list[float]]]:
    """拉取 top / bottom 候选 + 对应向量映射。候选不足时抛 InsufficientCandidatesError。"""
    base = select(Item).where(
        Item.user_id == user_id,
        Item.is_deleted.is_(False),
    )

    tops_stmt = base.where(Item.category == "top")
    bottoms_stmt = base.where(Item.category.in_(["bottom", "dress"]))

    tops = list((await db.execute(tops_stmt)).scalars().all())
    bottoms = list((await db.execute(bottoms_stmt)).scalars().all())

    if not tops:
        raise InsufficientCandidatesError("衣橱上衣不足，请先上传上装")
    if not bottoms:
        raise InsufficientCandidatesError("衣橱下装不足，请先上传下装")

    def _pass_hard_filter(item: Item) -> bool:
        # 温度过滤（宽松：区间外 5°C 以内也允许）
        if item.suitable_temp_min is not None and item.suitable_temp_max is not None:
            if temp < item.suitable_temp_min - 5 or temp > item.suitable_temp_max + 5:
                return False
        # 雨/雪天剔除易损材质
        if any(w in (weather_text or "") for w in ("雨", "雪")):
            material = (item.material or "").lower()
            if any(k in material for k in ("丝", "silk", "毛呢", "呢")):
                return False
        return True

    tops = [i for i in tops if _pass_hard_filter(i)]
    bottoms = [i for i in bottoms if _pass_hard_filter(i)]

    if not tops:
        raise InsufficientCandidatesError("当前温度/天气下没有合适的上装")
    if not bottoms:
        raise InsufficientCandidatesError("当前温度/天气下没有合适的下装")

    ids = [i.id for i in tops + bottoms]
    emb_stmt = select(ItemEmbedding.item_id, ItemEmbedding.embedding).where(
        ItemEmbedding.item_id.in_(ids)
    )
    emb_rows = (await db.execute(emb_stmt)).all()
    emb_map: dict[UUID, list[float]] = {row[0]: list(row[1]) for row in emb_rows}
    return tops, bottoms, emb_map


def _score_combo(
    top: Item,
    bottom: Item,
    emb_map: dict[UUID, list[float]],
    temp: float,
    feedback_map: dict[str, int],
    disliked_items: set[UUID] | None = None,
) -> dict[str, float]:
    scores = {
        "style": scorer.style_similarity(
            emb_map.get(top.id), emb_map.get(bottom.id), top.formality, bottom.formality
        ),
        "color": scorer.color_harmony(top.color_hex_list, bottom.color_hex_list),
        "occasion": scorer.occasion_fit(top.occasion_tags, bottom.occasion_tags),
        "weather": (
            scorer.item_weather_fit(top.suitable_temp_min, top.suitable_temp_max, temp)
            + scorer.item_weather_fit(bottom.suitable_temp_min, bottom.suitable_temp_max, temp)
        )
        / 2.0,
        "bias": scorer.user_bias([top.id, bottom.id], feedback_map),
    }
    # 软屏蔽：最近连续 dislike 的单品直接降权
    if disliked_items:
        penalty = 0.0
        if top.id in disliked_items:
            penalty += 0.4
        if bottom.id in disliked_items:
            penalty += 0.4
        scores["penalty"] = penalty
    return scores


def _weights(is_new_user: bool = False) -> dict[str, float]:
    """新用户无历史反馈时，移除 User_Bias 维度，权重均分给 Style 与 Color。"""
    style = settings.reco_weight_style
    color = settings.reco_weight_color
    bias = settings.reco_weight_bias
    if is_new_user:
        style += bias / 2
        color += bias / 2
        bias = 0.0
    return {
        "style": style,
        "color": color,
        "occasion": settings.reco_weight_occasion,
        "weather": settings.reco_weight_weather,
        "bias": bias,
    }


def _build_item_description(item: Item) -> str:
    attrs = item.attributes or {}
    parts: list[str] = []
    if attrs.get("visual_description"):
        parts.append(sanitize_prompt_text(attrs["visual_description"], max_len=120))
    else:
        if item.sub_category:
            parts.append(sanitize_prompt_text(item.sub_category, max_len=30))
        elif item.category:
            parts.append(sanitize_prompt_text(item.category, max_len=20))
        if item.color_hex_list:
            hex_str = ", ".join(
                sanitize_prompt_text(c, max_len=10) for c in item.color_hex_list
            )
            parts.append(f"颜色 {hex_str}")
        if item.material:
            parts.append(f"材质 {sanitize_prompt_text(item.material, max_len=40)}")
        if item.thickness:
            parts.append(f"厚度 {item.thickness}")
    if not parts:
        parts.append("暂无详细描述")
    return "，".join(parts)


def _pick_top_items(
    top_candidates: list[dict[str, Any]], key: str, n: int = 5
) -> list[Item]:
    """从高分组合中，按单品的最佳组合得分挑选 top-N 单品。"""
    best_score: dict[UUID, float] = {}
    item_map: dict[UUID, Item] = {}
    for combo in top_candidates:
        item: Item = combo[key]
        score = combo["score"]
        if item.id not in best_score or score > best_score[item.id]:
            best_score[item.id] = score
            item_map[item.id] = item
    sorted_items = sorted(
        item_map.values(), key=lambda x: best_score[x.id], reverse=True
    )
    return sorted_items[:n]


def _build_rerank_user_prompt(
    weather: WeatherResult,
    occasion: str,
    top_items: list[Item],
    bottom_items: list[Item],
) -> str:
    """按用户要求：上装在一起、下装在一起，让 LLM 自由组合。"""
    lines: list[str] = []
    lines.append("【当前环境】")
    lines.append(f"天气：{weather.text}")
    lines.append(f"温度：{weather.temperature}℃")
    lines.append(f"场合：{occasion}")
    lines.append("")

    lines.append("【候选上装列表】")
    for item in top_items:
        lines.append(f"--- 上装 ID: {item.id} ---")
        lines.append(f"名称：{sanitize_prompt_text(item.name, max_len=25)}")
        lines.append(f"描述：{_build_item_description(item)}")
        lines.append("")

    lines.append("【候选下装列表】")
    for item in bottom_items:
        lines.append(f"--- 下装 ID: {item.id} ---")
        lines.append(f"名称：{sanitize_prompt_text(item.name, max_len=25)}")
        lines.append(f"描述：{_build_item_description(item)}")
        lines.append("")

    lines.append(
        "请从候选上装列表和候选下装列表中自由组合，输出最佳的3套上下装搭配。"
        "输出格式必须是JSON对象：{\"result\": [{\"top_id\": \"...\", \"bottom_id\": \"...\", \"score\": 8.5, \"reason\": \"...\"}, ...]}"
    )
    return "\n".join(lines)


def _rule_reason(top: Item, bottom: Item, scores: dict[str, float]) -> str:
    parts: list[str] = []
    if scores["color"] >= 0.85:
        parts.append("色调协调")
    if scores["style"] >= 0.75:
        parts.append("风格统一")
    if scores["weather"] >= 0.9:
        parts.append("适合当前温度")
    if scores["occasion"] >= 0.5:
        parts.append("场合匹配")
    if not parts:
        parts.append("经典基础搭配")
    return f"{top.name}搭配{bottom.name}，{'、'.join(parts)}"[:60]


async def _persist_outfits(
    db: AsyncSession,
    user_id: UUID,
    ranked: list[dict[str, Any]],
    weather: WeatherResult,
) -> list[Outfit]:
    saved: list[Outfit] = []
    for entry in ranked:
        top: Item = entry["top"]
        bottom: Item = entry["bottom"]
        outfit = Outfit(
            user_id=user_id,
            name=entry.get("name") or "AI 今日推荐",
            occasion=(top.occasion_tags or [None])[0] if top.occasion_tags else "日常",
            weather=f"{weather.text} {int(round(weather.temperature))}°C",
            is_ai_generated=True,
            color_scheme=(top.color_hex_list or [])[:1] + (bottom.color_hex_list or [])[:2],
            reason=entry["reason"],
            score=entry["score"],
            temperature=weather.temperature,
            cover_url=top.image_url or bottom.image_url,
            cover_color=top.image_color,
        )
        db.add(outfit)
        await db.flush()
        db.add(OutfitItem(outfit_id=outfit.id, item_id=top.id, sort_order=0))
        db.add(OutfitItem(outfit_id=outfit.id, item_id=bottom.id, sort_order=1))
        saved.append(outfit)
    await db.commit()
    for outfit in saved:
        await db.refresh(outfit)
    return saved


async def recommend_daily(
    db: AsyncSession,
    user_id: UUID,
    weather: WeatherResult,
    top_n: int | None = None,
    force_refresh: bool = False,
    use_llm_rerank: bool = False,
) -> list[Outfit]:
    top_n = top_n or settings.reco_top_k
    key = _cache_key(user_id, weather.temperature, weather.text)

    if not force_refresh:
        cached_ids = _get_cached(key)
        if cached_ids:
            # 用缓存 outfit_id 回捞，若存在则复用
            stmt = (
                select(Outfit)
                .where(Outfit.id.in_([UUID(x["id"]) for x in cached_ids]))
                .order_by(Outfit.score.desc().nullslast())
            )
            outfits = list((await db.execute(stmt)).scalars().all())
            if len(outfits) >= top_n:
                return outfits[:top_n]

    tops, bottoms, emb_map = await _load_candidates(
        db, user_id, weather.temperature, weather.text
    )
    if not tops or not bottoms:
        return []

    feedback_map = await _load_feedback_map(db, user_id)
    disliked_items = await _load_disliked_items(db, user_id)
    is_new_user = not feedback_map
    weights = _weights(is_new_user=is_new_user)

    combos: list[dict[str, Any]] = []
    for top in tops:
        for bottom in bottoms:
            scores = _score_combo(
                top, bottom, emb_map, weather.temperature, feedback_map, disliked_items
            )
            total = scorer.total_score(scores, weights) - scores.get("penalty", 0.0)
            combos.append(
                {
                    "top": top,
                    "bottom": bottom,
                    "scores": scores,
                    "score": max(0.0, total),
                }
            )

    combos.sort(key=lambda x: x["score"], reverse=True)
    candidate_k = min(settings.reco_candidate_k, len(combos))
    top_candidates = combos[:candidate_k]

    # 低分降级：所有候选得分都极低（<0.3）时，随机推荐并提示“正在学习”
    fallback_mode = bool(top_candidates and top_candidates[0]["score"] < 0.3)
    if fallback_mode:
        random.shuffle(top_candidates)

    # LLM 精排：仅当手动刷新（use_llm_rerank=True）、有 API Key、候选足够且非低分降级时
    ranked: list[dict[str, Any]] = []
    if settings.ai_api_key and len(top_candidates) >= top_n and not fallback_mode and use_llm_rerank:
        try:
            top_items = _pick_top_items(top_candidates, "top", n=3)
            bottom_items = _pick_top_items(top_candidates, "bottom", n=3)
            top_map = {str(item.id): item for item in top_items}
            bottom_map = {str(item.id): item for item in bottom_items}
            occasion = top_items[0].occasion_tags[0] if (
                top_items[0].occasion_tags
            ) else "日常"
            user_prompt = _build_rerank_user_prompt(
                weather, occasion, top_items, bottom_items
            )
            picks = await dashscope_client.rerank_outfits(user_prompt, top_n)
            # 记录 LLM 精排调用
            await log_ai_usage(
                db,
                user_id=user_id,
                action="rerank",
                model=settings.ai_rerank_model,
                metadata={
                    "top_count": len(top_items),
                    "bottom_count": len(bottom_items),
                    "top_n": top_n,
                },
            )
            for pick in picks:
                top = top_map.get(pick.get("top_id"))
                bottom = bottom_map.get(pick.get("bottom_id"))
                if top is None or bottom is None:
                    continue
                # 复用该组合的打分（找不到时兜底计算）
                combo = next(
                    (
                        c
                        for c in top_candidates
                        if c["top"].id == top.id and c["bottom"].id == bottom.id
                    ),
                    None,
                )
                if combo is None:
                    scores = _score_combo(
                        top, bottom, emb_map, weather.temperature, feedback_map, disliked_items
                    )
                    total = scorer.total_score(scores, weights) - scores.get("penalty", 0.0)
                    combo = {"top": top, "bottom": bottom, "scores": scores, "score": max(0.0, total)}
                ranked.append(
                    {**combo, "reason": pick["reason"] or _rule_reason(combo["top"], combo["bottom"], combo["scores"])}
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("rerank fallback due to %s", exc)

    # Fallback：直接取分数前 top_n；低分降级时统一使用学习提示
    if len(ranked) < top_n:
        used_ids = {(r["top"].id, r["bottom"].id) for r in ranked}
        for combo in top_candidates:
            key_pair = (combo["top"].id, combo["bottom"].id)
            if key_pair in used_ids:
                continue
            reason = (
                "正在学习您的风格，这套仅供参考"
                if fallback_mode
                else _rule_reason(combo["top"], combo["bottom"], combo["scores"])
            )
            ranked.append({**combo, "reason": reason})
            used_ids.add(key_pair)
            if len(ranked) >= top_n:
                break

    if not ranked:
        return []

    saved = await _persist_outfits(db, user_id, ranked, weather)
    _set_cached(key, [{"id": str(o.id)} for o in saved])
    return saved
