"""推荐引擎主流程：候选筛选 → 组合打分 → Top10 → LLM 精排 → 写库返回。

V2: 六维评分（Style/Color/Silhouette/Occasion/Weather/Bias）+ 偏好融合 + 避免重复推荐。
进程内 (user_id, temp_bucket) TTL 缓存，避免同温度短时间内反复调用 LLM。
"""
from __future__ import annotations

import logging
import random
import time
from datetime import timedelta
from typing import Any
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timezone import now_bj
from app.models.item import Item
from app.models.item_embedding import ItemEmbedding
from app.models.outfit import Outfit, OutfitItem
from app.models.outfit_feedback import OutfitFeedback
from app.models.wear_history import WearHistory
from app.services.ai.dashscope_client import dashscope_client, sanitize_prompt_text
from app.services.ai.usage_logger import log_ai_usage
from app.services.ai.weather_service import WeatherResult
from app.services.reco import preference_learner, scorer
from app.services.reco import compatibility_model

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


async def _load_recent_worn_items(
    db: AsyncSession, user_id: UUID, days: int | None = None
) -> set[UUID]:
    """返回最近N天穿过的单品ID集合（避免重复推荐）。"""
    days = days or settings.reco_worn_within_days
    since = now_bj() - timedelta(days=days)
    stmt = (
        select(WearHistory.item_ids)
        .where(WearHistory.user_id == user_id, WearHistory.date >= since.date())
    )
    result = await db.execute(stmt)
    worn_ids: set[UUID] = set()
    for row in result.all():
        for iid in row[0] or []:
            worn_ids.add(iid)
    return worn_ids


async def _load_recent_recommended_items(
    db: AsyncSession, user_id: UUID, days: int | None = None
) -> dict[UUID, int]:
    """返回最近N天推荐过的单品ID及出现次数（连续推荐降权）。"""
    days = days or settings.reco_repeat_days
    since = now_bj() - timedelta(days=days)
    stmt = (
        select(OutfitItem.item_id, func.count().label("cnt"))
        .join(Outfit, OutfitItem.outfit_id == Outfit.id)
        .where(
            Outfit.user_id == user_id,
            Outfit.is_ai_generated.is_(True),
            Outfit.created_at >= since,
        )
        .group_by(OutfitItem.item_id)
    )
    result = await db.execute(stmt)
    return {row[0]: row[1] for row in result.all()}


def _is_avoided_pair(top: Item, bottom: Item) -> bool:
    """检查是否符合 pairing_preferences.avoid 规则 + 子品类兼容性。"""
    # 1. VLM 提取的 pairing_preferences.avoid
    top_prefs = top.pairing_preferences or {}
    bottom_prefs = bottom.pairing_preferences or {}
    top_avoid = set(top_prefs.get("avoid", []))
    bottom_avoid = set(bottom_prefs.get("avoid", []))
    if bottom.sub_category and bottom.sub_category in top_avoid:
        return True
    if top.sub_category and top.sub_category in bottom_avoid:
        return True

    # 2. 子品类硬性不兼容规则
    top_sub = (top.sub_category or "").lower()
    bot_sub = (bottom.sub_category or "").lower()
    bot_cat = bottom.category

    # dress 类下装不应与上衣搭配（连衣裙是整体一件）
    if bot_cat == "dress":
        # 除非是吊带裙/背心裙，可以内搭上衣
        if bot_sub not in ("slip_dress", "slip_skirt", "overall_dress", "pinafore_dress"):
            return True

    # 吊带裤/背带裤 + polo/衬衫/卫衣 不太协调
    if bot_sub in ("overall_pants", "suspender_pants") and top_sub in ("polo", "hoodie"):
        return True

    return False


def _prefilter_pairs(
    tops: list[Item],
    bottoms: list[Item],
    top_n: int,
    bottom_m: int,
) -> list[tuple[Item, Item]]:
    """大规模候选预筛选：随机采样 N 个上装，每个上装找 Top-M 最佳下装。

    策略（不依赖 embedding，避免远程 DB 加载全部向量）：
    1. 上装随机采样 top_n 个
    2. 对每个采样上装，用 style_vector + color 快速排序，取 bottom_m 个最佳下装
    """
    if not tops or not bottoms:
        return []

    # 1. 上装随机采样
    if len(tops) > top_n:
        sampled_tops = random.sample(tops, top_n)
    else:
        sampled_tops = tops

    _STYLE_KEYS_LIST = [
        "minimalist", "commute", "street", "sweet", "retro", "sporty",
        "luxury", "y2k", "japanese", "korean", "academic", "gorpcore",
    ]

    def _sv_to_vec(sv: dict | None) -> np.ndarray:
        if not sv:
            return np.zeros(len(_STYLE_KEYS_LIST), dtype=np.float32)
        return np.array([sv.get(k, 0.0) for k in _STYLE_KEYS_LIST], dtype=np.float32)

    # 2. 构建 bottom style_vector 矩阵
    B_sv = np.array([_sv_to_vec(b.style_vector) for b in bottoms], dtype=np.float32)
    B_sv_norm = B_sv / (np.linalg.norm(B_sv, axis=1, keepdims=True) + 1e-8)

    pairs: list[tuple[Item, Item]] = []
    for top in sampled_tops:
        # style_vector 相似度
        t_sv = _sv_to_vec(top.style_vector)
        t_sv_norm = t_sv / (np.linalg.norm(t_sv) + 1e-8)
        sv_sim = B_sv_norm @ t_sv_norm

        # 色彩兼容性
        color_sim = np.ones(len(bottoms), dtype=np.float32) * 0.5
        top_colors = top.color_hex_list or []
        for i, b in enumerate(bottoms):
            bot_colors = b.color_hex_list or []
            if top_colors and bot_colors:
                color_sim[i] = scorer.color_harmony(top_colors, bot_colors)

        # 综合: 50% style + 50% color（无 embedding）
        quick = 0.5 * sv_sim + 0.5 * color_sim
        top_m_idx = np.argsort(quick)[::-1][:bottom_m]
        for idx in top_m_idx:
            pairs.append((top, bottoms[idx]))

    return pairs


def _standalone_style_score(item: Item) -> float:
    """一件式风格分：取最高风格得分，体现单品风格明确度。"""
    sv = item.style_vector or {}
    if not sv:
        return 0.65
    max_score = max(sv.values()) if sv else 0.0
    # 风格越鲜明（最高分越高），得分越高，但不超 0.80
    return min(0.80, 0.55 + max_score * 0.25)


def _standalone_color_score(item: Item) -> float:
    """一件式色彩分：颜色越少越协调（1-2色=0.78, 3色=0.70, 4+色=0.62）。"""
    colors = item.color_hex_list or []
    if not colors:
        return 0.70
    if len(colors) <= 2:
        return 0.78
    elif len(colors) == 3:
        return 0.70
    else:
        return 0.62


def _standalone_silhouette_score(item: Item) -> float:
    """一件式廓形分：基于廓形和宽松度的自身协调度。"""
    sil = item.silhouette or ""
    vol = item.volume or 3
    # A字廓形自身协调度高，H廓形中等
    if sil == "A":
        base = 0.78
    elif sil == "H":
        base = 0.72
    elif sil == "X":
        base = 0.80
    else:
        base = 0.70
    # 极端宽松度略降
    if vol >= 5:
        base -= 0.05
    return base


def _prefilter_standalones(
    standalones: list[Item],
    temp: float,
    target_occasion: str | None,
    max_n: int,
) -> list[Item]:
    """一件式预筛选：用 weather+occasion 快速排序，取 Top-N。"""
    if len(standalones) <= max_n:
        return standalones

    def _quick_score(item: Item) -> float:
        w = scorer.item_weather_fit(item.suitable_temp_min, item.suitable_temp_max, temp)
        o = scorer.occasion_scores_fit(item.occasion_scores, item.occasion_scores, target_occasion)
        return 0.6 * w + 0.4 * o

    return sorted(standalones, key=_quick_score, reverse=True)[:max_n]


async def _load_candidates(
    db: AsyncSession, user_id: UUID, temp: float, weather_text: str
) -> tuple[list[Item], list[Item], list[Item], dict[UUID, list[float]]]:
    """拉取 top / bottom / standalone 候选 + 对应向量映射。

    standalone: is_full_outfit=True 的单品（连衣裙、套装），可单独推荐无需搭配。
    """
    _lc_t0 = time.time()
    base = select(Item).where(
        Item.user_id == user_id,
        Item.is_deleted.is_(False),
    )

    tops_stmt = base.where(Item.category == "top")
    bottoms_stmt = base.where(Item.category.in_(["bottom"]))
    standalone_stmt = base.where(Item.is_full_outfit.is_(True))

    tops = list((await db.execute(tops_stmt)).scalars().all())
    _lc_t1 = time.time()
    bottoms = list((await db.execute(bottoms_stmt)).scalars().all())
    _lc_t2 = time.time()
    standalones = list((await db.execute(standalone_stmt)).scalars().all())
    _lc_t3 = time.time()
    logger.info(
        "_load_candidates DB: tops=%d(%.2fs) bottoms=%d(%.2fs) standalones=%d(%.2fs)",
        len(tops), _lc_t1 - _lc_t0, len(bottoms), _lc_t2 - _lc_t1, len(standalones), _lc_t3 - _lc_t2,
    )

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
    standalones = [i for i in standalones if _pass_hard_filter(i)]

    if not tops and not standalones:
        raise InsufficientCandidatesError("当前温度/天气下没有合适的上装或套装")
    if not bottoms and not standalones:
        raise InsufficientCandidatesError("当前温度/天气下没有合适的下装或套装")

    # embedding 延迟加载：不在 _load_candidates 中加载，由调用方按需加载
    return tops, bottoms, standalones, {}


async def _load_embeddings_for_ids(
    db: AsyncSession, user_id: UUID, item_ids: set[UUID]
) -> dict[UUID, list[float]]:
    """按需加载指定 items 的 embedding（远程 DB 优化：只加载需要的）。"""
    if not item_ids:
        return {}
    _t0 = time.time()
    emb_map: dict[UUID, list[float]] = {}
    try:
        import asyncpg as _asyncpg
        from pgvector.asyncpg import register_vector as _reg_vec
        _dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        _raw = await _asyncpg.connect(_dsn)
        try:
            await _reg_vec(_raw)
            # 分批查询避免 IN 子句过长（每批 50 个）
            id_list = list(item_ids)
            for i in range(0, len(id_list), 50):
                batch = id_list[i:i+50]
                rows = await _raw.fetch(
                    "SELECT item_id, embedding FROM item_embeddings WHERE item_id = ANY($1::uuid[])",
                    batch,
                )
                for row in rows:
                    emb_map[row["item_id"]] = list(row["embedding"])
        finally:
            await _raw.close()
    except Exception as emb_exc:
        logger.warning("asyncpg embedding load failed, fallback to ORM: %s", emb_exc)
        emb_stmt = select(ItemEmbedding.item_id, ItemEmbedding.embedding).where(
            ItemEmbedding.item_id.in_(list(item_ids))
        )
        emb_rows = (await db.execute(emb_stmt)).all()
        for row in emb_rows:
            emb_map[row[0]] = list(row[1])
    logger.info("_load_embeddings_for_ids: %d items in %.2fs", len(emb_map), time.time() - _t0)
    return emb_map


def _score_combo(
    top: Item,
    bottom: Item,
    emb_map: dict[UUID, list[float]],
    temp: float,
    feedback_map: dict[str, int],
    disliked_items: set[UUID] | None = None,
    recent_worn: set[UUID] | None = None,
    recent_recommended: dict[UUID, int] | None = None,
    target_occasion: str | None = None,
    compat_available: bool = False,
) -> dict[str, float]:
    """V2 六维打分：Style / Color / Silhouette / Occasion / Weather / Bias。"""
    scores = {
        "style": scorer.style_vector_similarity(
            emb_map.get(top.id), emb_map.get(bottom.id),
            top.style_vector, bottom.style_vector,
        ),
        "color": scorer.color_harmony(top.color_hex_list, bottom.color_hex_list),
        "silhouette": scorer.silhouette_balance(
            top.silhouette, bottom.silhouette,
            top.volume, bottom.volume,
            top.drape, bottom.drape,
        ),
        "occasion": scorer.occasion_scores_fit(
            top.occasion_scores, bottom.occasion_scores, target_occasion
        ),
        "weather": (
            scorer.item_weather_fit(top.suitable_temp_min, top.suitable_temp_max, temp)
            + scorer.item_weather_fit(bottom.suitable_temp_min, bottom.suitable_temp_max, temp)
        )
        / 2.0,
        "bias": scorer.user_bias([top.id, bottom.id], feedback_map),
    }
    # V3: Compatibility Model（模型可用时新增维度）
    if compat_available:
        scores["compatibility"] = compatibility_model.score(
            top, bottom, emb_map.get(top.id), emb_map.get(bottom.id),
        )
    # 惩罚项（软屏蔽 + 避免重复推荐）
    penalty = 0.0
    if disliked_items:
        if top.id in disliked_items:
            penalty += 0.4
        if bottom.id in disliked_items:
            penalty += 0.4
    if recent_worn:
        if top.id in recent_worn:
            penalty += settings.reco_worn_penalty
        if bottom.id in recent_worn:
            penalty += settings.reco_worn_penalty
    if recent_recommended:
        threshold = settings.reco_repeat_threshold
        if recent_recommended.get(top.id, 0) >= threshold:
            penalty += settings.reco_repeat_penalty
        if recent_recommended.get(bottom.id, 0) >= threshold:
            penalty += settings.reco_repeat_penalty
    if penalty > 0:
        scores["penalty"] = penalty
    return scores


def _weights(is_new_user: bool = False, has_compatibility: bool = False) -> dict[str, float]:
    """V2 六维权重（+V3 compatibility 可选）。新用户无历史反馈时，移除 Bias 维度，权重均分。"""
    style = settings.reco_weight_style
    color = settings.reco_weight_color
    silhouette = settings.reco_weight_silhouette
    occasion = settings.reco_weight_occasion
    weather = settings.reco_weight_weather
    bias = settings.reco_weight_bias
    if is_new_user:
        # 新用户：bias 权重均分给 style 和 color
        style += bias / 2
        color += bias / 2
        bias = 0.0
    weights = {
        "style": style,
        "color": color,
        "silhouette": silhouette,
        "occasion": occasion,
        "weather": weather,
        "bias": bias,
    }
    # V3: Compatibility Model 可用时，从各维度均匀分配权重
    if has_compatibility:
        compat_weight = 0.10  # compatibility 占 10%
        # 从现有维度按比例缩减
        total = sum(weights.values())
        if total > 0:
            scale = (1.0 - compat_weight) / total
            weights = {k: v * scale for k, v in weights.items()}
        weights["compatibility"] = compat_weight
    return weights


def _compute_final_score(
    scores: dict[str, float],
    weights: dict[str, float],
    pref_profile: preference_learner.PreferenceProfile,
    top: Item,
    bottom: Item,
) -> float:
    """计算最终得分：六维加权 - 惩罚 + 偏好融合。"""
    outfit_score = scorer.total_score(scores, weights) - scores.get("penalty", 0.0)
    if settings.reco_use_v2 and not pref_profile.is_empty:
        pref_score = preference_learner.preference_score(pref_profile, top, bottom)
        return (1 - settings.reco_preference_blend) * max(0.0, outfit_score) + \
               settings.reco_preference_blend * pref_score
    return max(0.0, outfit_score)


def _build_item_description(item: Item) -> str:
    """V2: 构建单品描述，注入 V2 视觉属性。"""
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

    # V2 属性注入
    if item.silhouette:
        parts.append(f"廓形{item.silhouette}")
    if item.volume:
        vol_desc = {1: "修身", 2: "微修身", 3: "常规", 4: "宽松", 5: "Oversize"}.get(
            item.volume, ""
        )
        if vol_desc:
            parts.append(vol_desc)
    if item.drape and item.drape >= 4:
        parts.append("垂坠感强")
    if item.structure and item.structure >= 4:
        parts.append("挺括有型")
    if item.visual_focus:
        focus_map = {"shoulder": "肩部", "chest": "胸部", "waist": "腰部", "hip": "臀部", "leg": "腿部"}
        focus_str = "、".join(focus_map.get(f, f) for f in item.visual_focus[:2])
        if focus_str:
            parts.append(f"视觉重心{focus_str}")
    if item.style_vector:
        top_styles = sorted(item.style_vector.items(), key=lambda x: x[1], reverse=True)[:3]
        style_str = "、".join(k for k, v in top_styles if isinstance(v, (int, float)) and v > 0.5)
        if style_str:
            parts.append(f"风格偏{style_str}")

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
    candidates: list[dict[str, Any]],
) -> str:
    """构建 Top10 rerank 用户提示词：每套穿搭含 outfit_id、match_score、单品描述。"""
    lines: list[str] = []
    lines.append("【当前环境】")
    lines.append(f"天气：{weather.text}")
    lines.append(f"温度：{weather.temperature}℃")
    lines.append(f"场合：{occasion}")
    lines.append("")

    lines.append(f"【候选穿搭列表（共{len(candidates)}套）】")
    for i, combo in enumerate(candidates):
        top: Item = combo["top"]
        bottom: Item | None = combo.get("bottom")
        match_score = combo["score"]
        is_standalone = bottom is None or bottom.id == top.id

        lines.append(f"--- 穿搭 ID: {i+1} ---")
        lines.append(f"算法评分(match_score): {match_score:.3f}")

        if is_standalone:
            lines.append(f"类型: 一件式（连衣裙/套装）")
            lines.append(f"单品: {sanitize_prompt_text(top.name, max_len=25)}")
            lines.append(f"描述: {_build_item_description(top)}")
        else:
            lines.append(f"类型: 上下装搭配")
            lines.append(f"上装: {sanitize_prompt_text(top.name, max_len=25)}")
            lines.append(f"上装描述: {_build_item_description(top)}")
            lines.append(f"下装: {sanitize_prompt_text(bottom.name, max_len=25)}")
            lines.append(f"下装描述: {_build_item_description(bottom)}")
        lines.append("")

    lines.append(
        "请从以上候选穿搭中选出最值得推荐的3套，输出JSON："
        '{"result": [{"outfit_id": "1", "score": 9.5, "reason": "..."}, ...]}'
        "。outfit_id 填写候选列表中的 ID 编号。"
    )
    return "\n".join(lines)


def _rule_reason(top: Item, bottom: Item, scores: dict[str, float]) -> str:
    """V2: 规则理由生成 — 每套搭配从不同维度描述，避免同质化。"""
    import random

    top_name = top.name[:12] if top.name else "上装"
    bot_name = bottom.name[:12] if bottom.name else "下装"

    # 收集所有可用的描述片段
    fragments: dict[str, str] = {}

    # --- 廓形与比例 ---
    if top.volume and bottom.volume:
        if top.volume <= 2 and bottom.volume >= 4:
            fragments["silhouette"] = f"修身{top_name}配阔腿{bot_name}，上紧下松拉长比例"
        elif top.volume >= 4 and bottom.volume <= 2:
            fragments["silhouette"] = f"宽松{top_name}搭修身{bot_name}，松弛有度"
        elif top.volume <= 2 and bottom.volume <= 2:
            fragments["silhouette"] = f"整体修身剪裁，利落显身材"
        elif top.volume >= 4 and bottom.volume >= 4:
            fragments["silhouette"] = f"上下宽松呼应，随性有街头感"
        else:
            fragments["silhouette"] = f"廓形张弛有度，日常好驾驭"

    # --- 色彩 ---
    top_colors = top.color_hex_list or []
    bot_colors = bottom.color_hex_list or []
    if scores.get("color", 0) >= 0.92 and top_colors and bot_colors:
        fragments["color"] = "色彩默契度高，视觉干净统一"
    elif scores.get("color", 0) >= 0.8:
        fragments["color"] = "色调搭配舒服不出错"
    elif top_colors and bot_colors:
        fragments["color"] = "撞色搭配有层次感"

    # --- 风格气质 ---
    top_sv = top.style_vector or {}
    bot_sv = bottom.style_vector or {}
    style_cn = {
        "minimalist": "极简", "commute": "通勤", "street": "街头",
        "sweet": "甜美", "retro": "复古", "sporty": "运动",
        "luxury": "轻奢", "y2k": "Y2K", "japanese": "日系",
        "korean": "韩系", "academic": "学院", "gorpcore": "机能",
    }
    if top_sv and bot_sv:
        common = []
        for k in set(top_sv.keys()) & set(bot_sv.keys()):
            if isinstance(top_sv[k], (int, float)) and isinstance(bot_sv[k], (int, float)):
                if top_sv[k] > 0.5 and bot_sv[k] > 0.5:
                    common.append(k)
        if common:
            labels = [style_cn.get(s, s) for s in common[:2]]
            fragments["style"] = f"{''.join(labels)}调性贯穿全身"

    # --- 材质 ---
    if top.material and bottom.material:
        top_m = top.material.lower()
        bot_m = bottom.material.lower()
        if any(k in top_m for k in ("棉", "cotton")) and any(k in bot_m for k in ("棉", "cotton")):
            fragments["material"] = "棉质面料亲肤透气，适合贴身穿着"
        elif any(k in top_m for k in ("麻", "linen")) or any(k in bot_m for k in ("麻", "linen")):
            fragments["material"] = "麻棉质地自然有呼吸感"
        elif any(k in top_m for k in ("牛仔", "denim")) or any(k in bot_m for k in ("牛仔", "denim")):
            fragments["material"] = "牛仔元素增添休闲感"

    # --- 温度 ---
    if scores.get("weather", 0) >= 0.95:
        fragments["weather"] = "面料厚度刚好适配今天气温"
    elif scores.get("weather", 0) >= 0.85:
        fragments["weather"] = "穿着体感舒适不闷不冷"

    # --- 场合 ---
    if scores.get("occasion", 0) >= 0.8:
        fragments["occasion"] = "场合适配度高，穿出去得体"

    # 从可用片段中随机选 2-3 个，保证每套搭配描述不同
    all_keys = list(fragments.keys())
    pick_n = min(3, len(all_keys))
    # 用 scores 的哈希做种子，保证同一组合稳定但不同组合不同
    seed = int(scores.get("style", 0) * 100 + scores.get("color", 0) * 10)
    rng = random.Random(seed)
    chosen = rng.sample(all_keys, pick_n) if len(all_keys) > pick_n else all_keys

    parts = [fragments[k] for k in chosen]
    if not parts:
        parts = [f"{top_name}与{bot_name}基础百搭"]

    return "，".join(parts) + "。"


def _standalone_reason(item: Item, scores: dict[str, float]) -> str:
    """连衣裙/套装单独推荐的理由生成。"""
    import random

    name = item.name[:15] if item.name else "这件单品"
    fragments: dict[str, str] = {}

    # 风格
    sv = item.style_vector or {}
    style_cn = {
        "minimalist": "极简", "commute": "通勤", "street": "街头",
        "sweet": "甜美", "retro": "复古", "sporty": "运动",
        "luxury": "轻奢", "y2k": "Y2K", "japanese": "日系",
        "korean": "韩系", "academic": "学院", "gorpcore": "机能",
    }
    if sv:
        top_styles = sorted(
            [(k, v) for k, v in sv.items() if isinstance(v, (int, float)) and v > 0.5],
            key=lambda x: x[1], reverse=True,
        )[:2]
        if top_styles:
            labels = [style_cn.get(k, k) for k, _ in top_styles]
            fragments["style"] = f"{''.join(labels)}风格一体成型"

    # 廓形
    if item.silhouette and item.volume:
        vol_desc = {1: "修身", 2: "微修身", 3: "常规", 4: "宽松", 5: "oversize"}.get(item.volume, "常规")
        fragments["silhouette"] = f"{item.silhouette}廓形{vol_desc}剪裁"

    # 材质
    if item.material:
        m = item.material.lower()
        if any(k in m for k in ("棉", "cotton")):
            fragments["material"] = "棉质亲肤透气"
        elif any(k in m for k in ("麻", "linen")):
            fragments["material"] = "麻质自然有呼吸感"
        elif any(k in m for k in ("牛仔", "denim")):
            fragments["material"] = "牛仔质地休闲有型"

    # 温度
    if scores.get("weather", 0) >= 0.95:
        fragments["weather"] = "面料厚度刚好适配今天气温"

    # 场合
    if scores.get("occasion", 0) >= 0.8:
        fragments["occasion"] = "场合得体不费力"

    all_keys = list(fragments.keys())
    pick_n = min(3, len(all_keys))
    seed = int(scores.get("weather", 0) * 100 + scores.get("occasion", 0) * 10)
    rng = random.Random(seed)
    chosen = rng.sample(all_keys, pick_n) if len(all_keys) > pick_n else all_keys

    parts = [fragments[k] for k in chosen]
    if not parts:
        parts = [f"{name}一件式穿搭，省心又好看"]

    return f"{name}，{'，'.join(parts)}。"


async def _persist_outfits(
    db: AsyncSession,
    user_id: UUID,
    ranked: list[dict[str, Any]],
    weather: WeatherResult,
) -> list[Outfit]:
    saved: list[Outfit] = []
    for entry in ranked:
        top: Item = entry["top"]
        bottom: Item | None = entry.get("bottom")
        is_standalone = bottom is None or bottom.id == top.id

        color_scheme = (top.color_hex_list or [])[:1]
        if bottom and bottom.id != top.id:
            color_scheme = color_scheme + (bottom.color_hex_list or [])[:2]

        outfit = Outfit(
            user_id=user_id,
            name=entry.get("name") or "AI 今日推荐",
            occasion=(top.occasion_tags or [None])[0] if top.occasion_tags else "日常",
            weather=f"{weather.text} {int(round(weather.temperature))}°C",
            is_ai_generated=True,
            color_scheme=color_scheme,
            reason=entry["reason"],
            score=entry["score"],
            temperature=weather.temperature,
            cover_url=top.image_url or (bottom.image_url if bottom else None),
            cover_color=top.image_color,
        )
        db.add(outfit)
        await db.flush()
        db.add(OutfitItem(outfit_id=outfit.id, item_id=top.id, sort_order=0))
        if bottom and bottom.id != top.id:
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
    occasion: str | None = None,
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

    _t0 = time.time()
    tops, bottoms, standalones, emb_map = await _load_candidates(
        db, user_id, weather.temperature, weather.text
    )
    if not tops or not bottoms:
        return []

    _t1 = time.time()
    feedback_map = await _load_feedback_map(db, user_id)
    _t2 = time.time()
    disliked_items = await _load_disliked_items(db, user_id)
    _t3 = time.time()
    recent_worn = await _load_recent_worn_items(db, user_id)
    _t4 = time.time()
    recent_recommended = await _load_recent_recommended_items(db, user_id)
    _t5 = time.time()
    pref_profile = await preference_learner.build_preference_profile(db, user_id)
    _t6 = time.time()
    logger.info(
        "推荐计时: 数据加载 candidates=%.1fs feedback=%.1fs disliked=%.1fs "
        "worn=%.1fs recommended=%.1fs pref=%.1fs total=%.1fs",
        _t1 - _t0, _t2 - _t1, _t3 - _t2, _t4 - _t3, _t5 - _t4, _t6 - _t5, _t6 - _t0,
    )
    is_new_user = not feedback_map
    compat_available = compatibility_model.is_available()

    _t0 = time.time()
    weights = _weights(is_new_user=is_new_user, has_compatibility=compat_available)

    # 目标场景：优先使用传入的 occasion，否则从第一个上装推导
    target_occasion = occasion
    if not target_occasion and tops and tops[0].occasion_tags:
        target_occasion = tops[0].occasion_tags[0]

    combos: list[dict[str, Any]] = []

    # 大规模候选预筛选：上装×下装超过阈值时，随机采样+预排序
    total_pairs = len(tops) * len(bottoms)
    threshold = settings.reco_prefilter_threshold

    if total_pairs > threshold:
        logger.info(
            "预筛选启用: %d tops × %d bottoms = %d > %d, 采样 %d tops × top-%d bottoms",
            len(tops), len(bottoms), total_pairs, threshold,
            settings.reco_prefilter_top_n, settings.reco_prefilter_bottom_m,
        )
        candidate_pairs = _prefilter_pairs(
            tops, bottoms,
            settings.reco_prefilter_top_n,
            settings.reco_prefilter_bottom_m,
        )
    else:
        candidate_pairs = [(t, b) for t in tops for b in bottoms]

    # standalone 预筛选（在 embedding 加载之前）
    standalone_candidates = _prefilter_standalones(
        standalones, weather.temperature, target_occasion,
        settings.reco_prefilter_standalone_n,
    )

    # 延迟加载 embedding：只加载预筛选后的候选 items（远程 DB 优化）
    needed_ids: set[UUID] = set()
    for t, b in candidate_pairs:
        needed_ids.add(t.id)
        needed_ids.add(b.id)
    for item in standalone_candidates:
        needed_ids.add(item.id)
    emb_map = await _load_embeddings_for_ids(db, user_id, needed_ids)

    logger.info("推荐计时: 预筛选+embedding加载完成 %.2fs, %d 对候选 + %d 一件式",
                time.time() - _t0, len(candidate_pairs), len(standalone_candidates))

    for top, bottom in candidate_pairs:
        # pairing_preferences.avoid 硬过滤
        if _is_avoided_pair(top, bottom):
            continue
        scores = _score_combo(
            top, bottom, emb_map, weather.temperature, feedback_map,
            disliked_items, recent_worn, recent_recommended,
            target_occasion=target_occasion,
            compat_available=compat_available,
        )
        final = _compute_final_score(scores, weights, pref_profile, top, bottom)
        combos.append(
            {
                "top": top,
                "bottom": bottom,
                "scores": scores,
                "score": final,
            }
        )

    # standalone 候选评分（预筛选已在上方完成）
    for item in standalone_candidates:
        s_scores = {
            # 一件式自身协调，但不应压制好的搭配组合
            # style/color 用自身属性计算而非固定值
            "style": _standalone_style_score(item),
            "color": _standalone_color_score(item),
            "silhouette": _standalone_silhouette_score(item),
            "occasion": scorer.occasion_scores_fit(
                item.occasion_scores, item.occasion_scores, target_occasion
            ),
            "weather": scorer.item_weather_fit(
                item.suitable_temp_min, item.suitable_temp_max, weather.temperature
            ),
            "bias": scorer.user_bias([item.id], feedback_map),
        }
        if compat_available:
            s_scores["compatibility"] = 1.0
        s_final = _compute_final_score(s_scores, weights, pref_profile, item, item)
        combos.append(
            {
                "top": item,
                "bottom": None,  # standalone 标记
                "scores": s_scores,
                "score": s_final,
            }
        )

    combos.sort(key=lambda x: x["score"], reverse=True)

    logger.info("推荐计时: 评分+排序完成 %.2fs, %d 候选(搭配=%d, 一件式=%d)",
                time.time() - _t0, len(combos),
                len([c for c in combos if c.get("bottom") is not None]),
                len([c for c in combos if c.get("bottom") is None]))
    # 多样性保证：Top10 中至少包含 2 个一件式（如果有）
    candidate_k = min(settings.reco_candidate_k, len(combos))
    standalone_combos = [c for c in combos if c.get("bottom") is None]
    pair_combos = [c for c in combos if c.get("bottom") is not None]

    top_candidates: list[dict[str, Any]] = []
    # 先取搭配组合的前 8 个
    top_candidates.extend(pair_combos[:candidate_k - 2])
    # 再补一件式的前 2 个（按分数排序）
    top_candidates.extend(standalone_combos[:2])
    # 如果一件式不足 2 个，用剩余搭配补齐
    remaining = candidate_k - len(top_candidates)
    if remaining > 0:
        already_ids = {id(c) for c in top_candidates}
        for c in pair_combos:
            if id(c) not in already_ids:
                top_candidates.append(c)
                remaining -= 1
                if remaining <= 0:
                    break
    # 重新按分数排序
    top_candidates.sort(key=lambda x: x["score"], reverse=True)

    # 低分降级：所有候选得分都极低（<0.3）时，随机推荐并提示“正在学习”
    fallback_mode = bool(top_candidates and top_candidates[0]["score"] < 0.3)
    if fallback_mode:
        random.shuffle(top_candidates)

    # LLM 精排：默认走 LLM（Top10 -> LLM 选 Top3 + 生成理由）
    logger.info("推荐计时: Top%d 候选准备完成 %.2fs, 开始 LLM 精排",
                len(top_candidates), time.time() - _t0)
    ranked: list[dict[str, Any]] = []
    if settings.ai_api_key and len(top_candidates) >= top_n and not fallback_mode:
        try:
            rerank_occasion = target_occasion or "日常"
            user_prompt = _build_rerank_user_prompt(
                weather, rerank_occasion, top_candidates,
            )
            picks = await dashscope_client.rerank_outfits(user_prompt, top_n)
            await log_ai_usage(
                db, user_id=user_id, action="rerank",
                model=settings.ai_rerank_model,
                metadata={"candidate_count": len(top_candidates), "top_n": top_n},
            )
            for pick in picks:
                try:
                    idx = int(pick["outfit_id"]) - 1
                except (ValueError, KeyError, TypeError):
                    continue
                if 0 <= idx < len(top_candidates):
                    combo = top_candidates[idx]
                    reason = pick.get("reason", "")
                    if not reason:
                        reason = (
                            _standalone_reason(combo["top"], combo["scores"])
                            if combo.get("bottom") is None
                            else _rule_reason(combo["top"], combo["bottom"], combo["scores"])
                        )
                    ranked.append({**combo, "reason": reason})
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM rerank failed, fallback to rule-based: %s", exc)

    # Fallback：LLM 失败或结果不足时，用规则拼接补充
    if len(ranked) < top_n:
        used_ids = {(r["top"].id, r.get("bottom").id if r.get("bottom") else None) for r in ranked}
        for combo in top_candidates:
            bot = combo.get("bottom")
            bot_id = bot.id if bot else None
            key_pair = (combo["top"].id, bot_id)
            if key_pair in used_ids:
                continue
            reason = (
                "正在学习您的风格，这套仅供参考"
                if fallback_mode
                else _standalone_reason(combo["top"], combo["scores"])
                if bot is None
                else _rule_reason(combo["top"], bot, combo["scores"])
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
