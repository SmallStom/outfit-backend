"""用户偏好学习：从历史反馈 + 穿搭记录中提取长期偏好画像。

偏好画像用于推荐评分融合：FinalScore = 0.75 * OutfitScore + 0.25 * PreferenceScore
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.outfit_feedback import OutfitFeedback
from app.models.wear_history import WearHistory

logger = logging.getLogger(__name__)


@dataclass
class PreferenceProfile:
    """用户偏好画像。"""
    favorite_colors: list[str] = field(default_factory=list)       # 最常被 like/worn 的颜色 hex
    favorite_styles: list[str] = field(default_factory=list)       # 风格偏好（style_vector 高频维度）
    favorite_silhouettes: list[str] = field(default_factory=list)  # 廓形偏好（如 "上紧下松"）
    preferred_occasions: list[str] = field(default_factory=list)   # 常用场景
    is_empty: bool = True                                           # 是否有足够数据构建画像


async def build_preference_profile(
    db: AsyncSession, user_id: UUID
) -> PreferenceProfile:
    """从 outfit_feedbacks（like）+ wear_history 中构建偏好画像。

    数据来源：
    1. 用户 like 的 outfit 中的单品 → 统计颜色、风格、廓形偏好
    2. wear_history 中的高频穿着单品 → 补充偏好
    """
    profile = PreferenceProfile()

    # 1. 查询 like 的 outfit 中的单品 ID
    liked_item_ids: set[UUID] = set()
    stmt = (
        select(OutfitFeedback.item_id)
        .where(
            OutfitFeedback.user_id == user_id,
            OutfitFeedback.action == "like",
            OutfitFeedback.item_id.is_not(None),
        )
    )
    result = await db.execute(stmt)
    for item_id in result.scalars().all():
        if item_id:
            liked_item_ids.add(item_id)

    # 2. 查询 wear_history 中的单品 ID（高频穿着）
    worn_item_ids: set[UUID] = set()
    stmt = (
        select(WearHistory.item_ids)
        .where(WearHistory.user_id == user_id)
        .limit(200)
    )
    result = await db.execute(stmt)
    for row in result.all():
        for iid in row[0] or []:
            worn_item_ids.add(iid)

    # 合并：liked 权重高，worn 权重中
    all_item_ids = liked_item_ids | worn_item_ids
    if not all_item_ids:
        return profile

    # 3. 查询这些单品的属性
    stmt = select(Item).where(
        Item.id.in_(list(all_item_ids)),
        Item.is_deleted.is_(False),
    )
    result = await db.execute(stmt)
    items = list(result.scalars().all())

    if not items:
        return profile

    # 4. 统计偏好
    color_counter: Counter[str] = Counter()
    style_counter: Counter[str] = Counter()
    silhouette_counter: Counter[str] = Counter()
    occasion_counter: Counter[str] = Counter()

    for item in items:
        weight = 2.0 if item.id in liked_item_ids else 1.0

        # 颜色偏好
        if item.color_hex_list:
            for hex_val in item.color_hex_list[:1]:  # 只取主色
                color_counter[hex_val] += weight

        # 风格偏好
        if item.style_vector:
            for style_key, score in item.style_vector.items():
                if isinstance(score, (int, float)) and score > 0.5:
                    style_counter[style_key] += weight

        # 廓形偏好
        if item.silhouette:
            silhouette_counter[item.silhouette] += weight
        if item.volume:
            vol_label = {1: "slim", 2: "slim", 3: "regular", 4: "loose", 5: "loose"}.get(
                item.volume, "regular"
            )
            silhouette_counter[vol_label] += weight

        # 场景偏好
        if item.occasion_scores:
            for occ_key, occ_score in item.occasion_scores.items():
                if isinstance(occ_score, (int, float)) and occ_score >= 4:
                    occasion_counter[occ_key] += weight
        elif item.occasion_tags:
            for tag in item.occasion_tags:
                occasion_counter[tag] += weight

    # 5. 提取 Top 偏好
    profile.favorite_colors = [c for c, _ in color_counter.most_common(5)]
    profile.favorite_styles = [s for s, _ in style_counter.most_common(5)]
    profile.favorite_silhouettes = [s for s, _ in silhouette_counter.most_common(3)]
    profile.preferred_occasions = [o for o, _ in occasion_counter.most_common(3)]
    profile.is_empty = not (
        profile.favorite_colors or profile.favorite_styles or profile.favorite_silhouettes
    )

    return profile


def preference_score(
    profile: PreferenceProfile,
    top: Item,
    bottom: Item,
) -> float:
    """计算单套搭配与用户偏好的匹配度。

    返回: [0.0, 1.0]
    """
    if profile.is_empty:
        return 0.5  # 无偏好数据时中性分

    scores: list[float] = []
    weights: list[float] = []

    # 1. 颜色匹配 (权重 0.35)
    color_score = 0.5
    if profile.favorite_colors:
        top_colors = set(top.color_hex_list or [])
        bottom_colors = set(bottom.color_hex_list or [])
        fav_set = set(profile.favorite_colors)
        if top_colors & fav_set or bottom_colors & fav_set:
            color_score = 1.0
        elif top_colors or bottom_colors:
            color_score = 0.6
    scores.append(color_score)
    weights.append(0.35)

    # 2. 风格匹配 (权重 0.35)
    style_score = 0.5
    if profile.favorite_styles:
        top_styles = set()
        bottom_styles = set()
        if top.style_vector:
            top_styles = {k for k, v in top.style_vector.items() if isinstance(v, (int, float)) and v > 0.5}
        if bottom.style_vector:
            bottom_styles = {k for k, v in bottom.style_vector.items() if isinstance(v, (int, float)) and v > 0.5}
        fav_style_set = set(profile.favorite_styles)
        match_count = len((top_styles | bottom_styles) & fav_style_set)
        if match_count > 0:
            style_score = min(1.0, 0.5 + 0.25 * match_count)
    scores.append(style_score)
    weights.append(0.35)

    # 3. 廓形匹配 (权重 0.30)
    silhouette_score = 0.5
    if profile.favorite_silhouettes:
        item_silhouettes = set()
        if top.silhouette:
            item_silhouettes.add(top.silhouette)
        if bottom.silhouette:
            item_silhouettes.add(bottom.silhouette)
        if top.volume:
            item_silhouettes.add({1: "slim", 2: "slim", 3: "regular", 4: "loose", 5: "loose"}.get(top.volume, "regular"))
        if bottom.volume:
            item_silhouettes.add({1: "slim", 2: "slim", 3: "regular", 4: "loose", 5: "loose"}.get(bottom.volume, "regular"))
        fav_sil_set = set(profile.favorite_silhouettes)
        if item_silhouettes & fav_sil_set:
            silhouette_score = 1.0
    scores.append(silhouette_score)
    weights.append(0.30)

    # 加权平均
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.5
    return max(0.0, min(1.0, sum(s * w for s, w in zip(scores, weights)) / total_weight))
