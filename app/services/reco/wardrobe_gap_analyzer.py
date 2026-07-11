"""衣橱缺口分析器。

统计当前衣橱的品类/风格/颜色分布，对比理想衣橱矩阵，
识别缺失项（如"缺少浅色通勤裤"），并对接 shop_recommender 推荐补缺商品。
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.shop_item import ShopItem
from app.services.reco.shop_recommender import infer_user_role, tag_shop_item

logger = logging.getLogger(__name__)

# ---------- 理想衣橱矩阵 ----------
IDEAL_WARDROBE_MATRIX: dict[str, dict[str, Any]] = {
    "top": {
        "min": 3,
        "label": "上衣",
        "essential_subs": {
            "tshirt": "基础T恤",
            "shirt": "衬衫",
            "knit": "针织衫",
        },
    },
    "bottom": {
        "min": 2,
        "label": "下装",
        "essential_subs": {
            "jeans": "牛仔裤",
            "casual_pants": "休闲裤",
            "skirt": "半裙",
        },
    },
    "dress": {
        "min": 1,
        "label": "连衣裙",
        "essential_subs": {},
    },
    "outerwear": {
        "min": 1,
        "label": "外套",
        "essential_subs": {
            "jacket": "夹克",
            "coat": "大衣",
        },
    },
    "shoes": {
        "min": 1,
        "label": "鞋履",
        "essential_subs": {},
    },
    "accessory": {
        "min": 1,
        "label": "配饰",
        "essential_subs": {},
    },
}

# 兼容历史品类别名
CATEGORY_ALIASES: dict[str, str] = {
    "outer": "outerwear",
    "acc": "accessory",
}

# 中性基础色关键词
NEUTRAL_COLOR_KEYWORDS = [
    "黑", "白", "灰", "藏青", "藏蓝", "米", "卡其", "navy", "beige", "khaki",
    "brown", "棕",
]

# 浅色关键词
LIGHT_COLOR_KEYWORDS = [
    "白", "米", "浅", "裸", "奶", "杏", "beige", "cream", "ivory",
]

# 通勤关键词
COMMUTE_KEYWORDS = ["通勤", "通勤裤", "西裤", "直筒", "通勤裙"]


def _normalize_category(category: str | None) -> str:
    if not category:
        return ""
    return CATEGORY_ALIASES.get(category, category)


def _is_neutral_color(color: str | None) -> bool:
    if not color:
        return False
    lower = color.lower()
    return any(kw in lower for kw in NEUTRAL_COLOR_KEYWORDS)


def _is_light_color(color: str | None) -> bool:
    if not color:
        return False
    lower = color.lower()
    return any(kw in lower for kw in LIGHT_COLOR_KEYWORDS)


def _is_commute_item(item: Item | ShopItem) -> bool:
    text = " ".join(filter(None, [item.name, item.sub_category, getattr(item, "material", "")]))
    lower = text.lower()
    return any(kw in lower for kw in COMMUTE_KEYWORDS)


async def _load_wardrobe_items(db: AsyncSession, user_id: UUID) -> list[Item]:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


def _analyze_distribution(items: list[Item]) -> dict[str, Any]:
    """统计品类 / 子品类 / 颜色 / 风格分布。"""
    category_counter: Counter[str] = Counter()
    sub_category_counter: Counter[str] = Counter()
    color_counter: Counter[str] = Counter()
    style_counter: Counter[str] = Counter()

    for item in items:
        normalized = _normalize_category(item.category)
        category_counter[normalized] += 1
        if item.sub_category:
            sub_category_counter[item.sub_category.lower()] += 1
        if item.color:
            color_counter[item.color] += 1
        if item.style_vector and isinstance(item.style_vector, dict):
            for style, score in item.style_vector.items():
                if isinstance(score, (int, float)) and score > 0.5:
                    style_counter[style] += 1

    return {
        "total": len(items),
        "by_category": dict(category_counter),
        "by_sub_category": dict(sub_category_counter),
        "by_color": dict(color_counter),
        "by_style": dict(style_counter),
    }


def _identify_gaps(distribution: dict[str, Any]) -> list[dict[str, Any]]:
    """对比理想衣橱矩阵，识别缺失项。"""
    gaps: list[dict[str, Any]] = []
    by_category = distribution["by_category"]
    by_sub_category = distribution["by_sub_category"]
    total = distribution["total"]
    by_color = distribution["by_color"]

    # 1. 品类数量不足
    for category, spec in IDEAL_WARDROBE_MATRIX.items():
        current = by_category.get(category, 0)
        min_required = spec["min"]
        if current < min_required:
            gaps.append({
                "type": "category_shortage",
                "category": category,
                "label": spec["label"],
                "current": current,
                "required": min_required,
                "suggestion": (
                    f"缺少{spec['label']}，建议至少补充 {min_required - current} 件"
                ),
            })

    # 2. 关键子品类缺失
    for category, spec in IDEAL_WARDROBE_MATRIX.items():
        subs = spec.get("essential_subs", {})
        for sub_key, sub_label in subs.items():
            found = any(sub_key in k for k in by_sub_category)
            if not found:
                gaps.append({
                    "type": "sub_category_missing",
                    "category": category,
                    "sub_category": sub_key,
                    "label": sub_label,
                    "suggestion": f"缺少{sub_label}，建议补充一件百搭{sub_label}",
                })

    # 3. 颜色平衡检查
    if total > 0:
        neutral_count = sum(
            cnt for color, cnt in by_color.items() if _is_neutral_color(color)
        )
        if neutral_count / max(total, 1) < 0.4:
            gaps.append({
                "type": "color_imbalance",
                "label": "中性基础色不足",
                "suggestion": (
                    "衣橱中性色（黑/白/灰/米）偏少，"
                    "建议补充基础色单品以提升搭配率"
                ),
            })

        light_count = sum(
            cnt for color, cnt in by_color.items() if _is_light_color(color)
        )
        if light_count == 0:
            gaps.append({
                "type": "color_missing",
                "label": "缺少浅色单品",
                "suggestion": "衣橱缺少浅色单品，建议补充白色或米色通勤下装",
            })

    return gaps


async def _recommend_gap_fillers(
    db: AsyncSession,
    user_id: UUID,
    gaps: list[dict[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    """根据缺口推荐补缺商品，利用 shop_recommender 的角色推断和标签匹配。"""
    if not gaps:
        return []

    # 收集需要补充的品类
    needed_categories: set[str] = set()
    need_light = False
    need_neutral = False
    for gap in gaps:
        cat = gap.get("category")
        if cat:
            needed_categories.add(cat)
        if gap.get("type") == "color_missing":
            need_light = True
        if gap.get("type") == "color_imbalance":
            need_neutral = True

    if not needed_categories:
        return []

    # 查询可用商品
    result = await db.execute(
        select(ShopItem).where(
            ShopItem.is_enabled.is_(True),
            ShopItem.category.in_(needed_categories),
        )
    )
    candidates = list(result.scalars().all())
    if not candidates:
        return []

    # 推断用户角色以做风格匹配
    try:
        role = await infer_user_role(db, user_id)
    except Exception:  # noqa: BLE001
        from app.services.reco.shop_recommender import UserRole
        role = UserRole()

    # 打分
    scored: list[tuple[float, ShopItem]] = []
    for item in candidates:
        tags = tag_shop_item(item)
        score = 0.5
        # 风格匹配加分
        if role.style_persona in tags.style_tags:
            score += 0.3
        # 浅色需求
        if need_light and _is_light_color(item.color):
            score += 0.3
        # 中性色需求
        if need_neutral and _is_neutral_color(item.color):
            score += 0.2
        # 通勤需求（当下装缺少通勤款时）
        if item.category == "bottom" and _is_commute_item(item):
            score += 0.15
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)

    recommendations: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for score, item in scored:
        if item.name in seen_names:
            continue
        seen_names.add(item.name)
        recommendations.append({
            "shop_item_id": str(item.id),
            "name": item.name,
            "category": item.category,
            "sub_category": item.sub_category,
            "price": item.price,
            "image_url": item.image_url,
            "color": item.color,
            "source_url": item.source_url,
            "match_score": round(score, 2),
        })
        if len(recommendations) >= limit:
            break

    return recommendations


async def analyze_wardrobe_gap(
    db: AsyncSession, user_id: UUID
) -> list[dict[str, Any]]:
    """分析衣橱缺口，返回缺失项及补缺商品推荐。

    返回结构示例：
    [
        {
            "type": "category_shortage",
            "category": "outerwear",
            "label": "外套",
            "current": 0,
            "required": 1,
            "suggestion": "缺少外套，建议至少补充 1 件",
            "recommendations": [{...shop_item...}, ...]
        },
        ...
    ]
    """
    items = await _load_wardrobe_items(db, user_id)

    if not items:
        return [{
            "type": "empty_wardrobe",
            "label": "衣橱为空",
            "suggestion": "你的衣橱还是空的，建议先上传几件基础单品开始",
            "distribution": {"total": 0},
            "recommendations": [],
        }]

    distribution = _analyze_distribution(items)
    gaps = _identify_gaps(distribution)

    if not gaps:
        return [{
            "type": "balanced",
            "label": "衣橱均衡",
            "suggestion": "你的衣橱品类和颜色分布比较均衡，继续保持",
            "distribution": distribution,
            "recommendations": [],
        }]

    # 为缺口推荐补缺商品
    fillers = await _recommend_gap_fillers(db, user_id, gaps)

    results: list[dict[str, Any]] = []
    for gap in gaps:
        gap_result = {**gap}
        # 按品类或颜色需求匹配推荐
        gap_cats = {gap.get("category")} if gap.get("category") else set()
        gap_type = gap.get("type")
        gap_fillers = []
        for f in fillers:
            if gap_type in ("color_missing", "color_imbalance"):
                if _is_light_color(f.get("color")) or _is_neutral_color(f.get("color")):
                    gap_fillers.append(f)
            elif f.get("category") in gap_cats:
                gap_fillers.append(f)
        gap_result["recommendations"] = gap_fillers[:2]
        results.append(gap_result)

    # 在第一个缺口上附加分布概览
    if results:
        results[0]["distribution"] = distribution

    return results
