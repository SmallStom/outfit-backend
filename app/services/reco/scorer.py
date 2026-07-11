"""六维打分纯函数：Style / Color / Silhouette / Occasion / Weather / User_Bias。

所有函数返回 [0.0, 1.0] 之间的浮点分数。
V1 函数（style_similarity, occasion_fit）保留用于向后兼容；V2 新增 silhouette_balance、
style_vector_similarity、occasion_scores_fit。
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np


_BASIC_HUE_HEX = {"#000", "#000000", "#fff", "#ffffff", "#888888", "#cccccc"}
_BASIC_KEYWORDS = ("黑", "白", "灰", "米", "驼")


# ---------- 通用工具 ---------- #

def _hex_to_hsl(hex_str: str) -> tuple[float, float, float] | None:
    """#RRGGBB / #RGB -> (h, s, l) in [0..360, 0..1, 0..1]."""
    if not isinstance(hex_str, str):
        return None
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError:
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    sat = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0, sat, l


def _is_basic_color(hex_str: str) -> bool:
    hsl = _hex_to_hsl(hex_str)
    if hsl is None:
        return False
    _, s, _ = hsl
    return s < 0.15  # 饱和度非常低 → 灰阶/米色 一类


# ---------- 1. Style similarity ---------- #

def style_similarity(
    vec_top: list[float] | np.ndarray | None,
    vec_bottom: list[float] | np.ndarray | None,
    formality_top: float | None,
    formality_bottom: float | None,
) -> float:
    cos_component = 0.5
    if vec_top is not None and vec_bottom is not None:
        a = np.asarray(vec_top, dtype=np.float32)
        b = np.asarray(vec_bottom, dtype=np.float32)
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na > 0 and nb > 0:
            sim = float(np.dot(a, b) / (na * nb))
            # cos_sim ∈ [-1,1] → 归一化到 [0,1]
            cos_component = (sim + 1) / 2

    formal_component = 0.7
    if formality_top is not None and formality_bottom is not None:
        formal_component = 1.0 - abs(formality_top - formality_bottom)

    # 视觉相似 70%，正式度对齐 30%
    return max(0.0, min(1.0, 0.7 * cos_component + 0.3 * formal_component))


# ---------- 2. Color harmony ---------- #

def _pair_color_score(hex_a: str, hex_b: str) -> float:
    if _is_basic_color(hex_a) or _is_basic_color(hex_b):
        return 0.85  # 基础色百搭

    hsl_a = _hex_to_hsl(hex_a)
    hsl_b = _hex_to_hsl(hex_b)
    if hsl_a is None or hsl_b is None:
        return 0.6

    diff = abs(hsl_a[0] - hsl_b[0])
    if diff > 180:
        diff = 360 - diff

    if diff < 15:
        return 0.95  # 同类色
    if diff < 45:
        return 0.85  # 邻近色
    if diff < 90:
        return 0.55  # 中间地带
    if diff < 150:
        return 0.35  # 冲突色
    if diff <= 180:
        return 0.65  # 互补色（谨慎撞色）
    return 0.5


def color_harmony(
    hex_list_top: Iterable[str] | None, hex_list_bottom: Iterable[str] | None
) -> float:
    top = [h for h in (hex_list_top or []) if isinstance(h, str)]
    bot = [h for h in (hex_list_bottom or []) if isinstance(h, str)]
    if not top or not bot:
        return 0.6  # 缺失时给中性分

    weighted_sum = 0.0
    weight_total = 0.0
    for i, ha in enumerate(top):
        for j, hb in enumerate(bot):
            weight = 1.0 / (1 + i + j)  # 主色权重高
            weighted_sum += _pair_color_score(ha, hb) * weight
            weight_total += weight
    if weight_total <= 0:
        return 0.6
    return max(0.0, min(1.0, weighted_sum / weight_total))


# ---------- 3. Occasion fit ---------- #

def occasion_fit(
    tags_top: Iterable[str] | None, tags_bottom: Iterable[str] | None
) -> float:
    set_a = set([t for t in (tags_top or []) if t])
    set_b = set([t for t in (tags_bottom or []) if t])
    if not set_a or not set_b:
        return 0.5
    inter = set_a & set_b
    union = set_a | set_b
    if not union:
        return 0.5
    return len(inter) / len(union)


# ---------- 4. Weather fit ---------- #

def weather_fit(temp_min: int | None, temp_max: int | None, current: float) -> float:
    if temp_min is None or temp_max is None:
        return 0.6
    if temp_min <= current <= temp_max:
        return 1.0
    distance = min(abs(current - temp_min), abs(current - temp_max))
    # 每偏离 1°C 扣 0.08，最多扣到 0
    return max(0.0, 1.0 - 0.08 * distance)


def item_weather_fit(temp_min: int | None, temp_max: int | None, current: float) -> float:
    return weather_fit(temp_min, temp_max, current)


# ---------- 5. User bias ---------- #

def user_bias(item_ids: Iterable, feedback_map: dict) -> float:
    """feedback_map: {item_id_str: net_score}, net_score = likes - dislikes."""
    score = 0.5
    for iid in item_ids:
        key = str(iid)
        delta = feedback_map.get(key, 0)
        # 每 like +0.1，每 dislike -0.2
        score += 0.1 * max(delta, 0) - 0.2 * abs(min(delta, 0))
    return max(0.0, min(1.0, score))


# ---------- 综合 ---------- #

def total_score(scores: dict[str, float], weights: dict[str, float]) -> float:
    return sum(scores.get(k, 0.0) * w for k, w in weights.items())


# ================================================================== #
#                      V2 新增打分函数                                 #
# ================================================================== #

# ---------- 6. Silhouette balance (V2 新增) ---------- #

# 廓形搭配规则矩阵: (top_shape, bottom_shape) -> score
_SILHOUETTE_RULES: dict[tuple[str, str], float] = {
    ("slim", "loose"): 0.95,   # 上紧下松
    ("loose", "slim"): 0.85,   # 上松下紧
    ("slim", "slim"): 0.70,    # 上紧下紧
    ("loose", "loose"): 0.60,  # 上松下松
    ("regular", "loose"): 0.85,
    ("slim", "regular"): 0.80,
    ("loose", "regular"): 0.75,
    ("regular", "slim"): 0.80,
    ("regular", "regular"): 0.75,
}

# 廓形字母组合加分
_SILHOUETTE_BONUS: dict[tuple[str, str], float] = {
    ("X", "A"): 0.05,
    ("X", "X"): 0.05,
    ("A", "A"): 0.05,
    ("H", "A"): 0.03,
}


def silhouette_balance(
    top_silhouette: str | None,
    bottom_silhouette: str | None,
    top_volume: int | None,
    bottom_volume: int | None,
    top_drape: int | None = None,
    bottom_drape: int | None = None,
) -> float:
    """V2 廓形平衡评分：基于上紧下松/上松下紧等规则。

    参数:
        top_silhouette: 上装廓形字母 H/A/X/O/T
        bottom_silhouette: 下装廓形字母
        top_volume: 上装宽松度 1-5
        bottom_volume: 下装宽松度 1-5
        top_drape: 上装垂坠感 1-5
        bottom_drape: 下装垂坠感 1-5
    返回: [0.0, 1.0]
    """
    if not top_volume or not bottom_volume:
        return 0.5  # 缺失时中性分

    # volume → shape 分类
    def _to_shape(v: int) -> str:
        if v <= 2:
            return "slim"
        if v <= 3:
            return "regular"
        return "loose"

    top_shape = _to_shape(top_volume)
    bottom_shape = _to_shape(bottom_volume)

    base = _SILHOUETTE_RULES.get((top_shape, bottom_shape), 0.70)

    # 廓形字母组合微调
    if top_silhouette and bottom_silhouette:
        bonus = _SILHOUETTE_BONUS.get((top_silhouette, bottom_silhouette), 0.0)
        base = min(1.0, base + bonus)

    # 垂坠感协调（差异≤2 加分）
    if top_drape and bottom_drape and abs(top_drape - bottom_drape) <= 2:
        base = min(1.0, base + 0.03)

    return max(0.0, min(1.0, base))


# ---------- 7. Style vector similarity (V2 升级) ---------- #

def style_vector_similarity(
    vec_top: list[float] | np.ndarray | None,
    vec_bottom: list[float] | np.ndarray | None,
    style_vec_top: dict | None,
    style_vec_bottom: dict | None,
) -> float:
    """V2 风格相似度：视觉 embedding 余弦 50% + style_vector 余弦 50%。

    当 style_vector 缺失时，退化为纯视觉 embedding 相似度（兼容旧数据）。
    """
    # 视觉 embedding 余弦相似度
    cos_visual = 0.5
    if vec_top is not None and vec_bottom is not None:
        a, b = np.asarray(vec_top, dtype=np.float32), np.asarray(vec_bottom, dtype=np.float32)
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na > 0 and nb > 0:
            cos_visual = (float(np.dot(a, b) / (na * nb)) + 1) / 2

    # style_vector 余弦相似度
    cos_style = 0.5
    has_style = False
    if style_vec_top and style_vec_bottom:
        keys = set(style_vec_top.keys()) & set(style_vec_bottom.keys())
        if keys:
            a = np.array([style_vec_top[k] for k in keys], dtype=np.float32)
            b = np.array([style_vec_bottom[k] for k in keys], dtype=np.float32)
            na, nb = np.linalg.norm(a), np.linalg.norm(b)
            if na > 0 and nb > 0:
                cos_style = (float(np.dot(a, b) / (na * nb)) + 1) / 2
                has_style = True

    if has_style:
        return max(0.0, min(1.0, 0.5 * cos_visual + 0.5 * cos_style))
    return max(0.0, min(1.0, cos_visual))


# ---------- 8. Occasion scores fit (V2 升级) ---------- #

_OCCASION_LABEL_MAP = {
    "office": "办公", "meeting": "会议", "date": "约会",
    "travel": "旅行", "daily": "日常", "party": "派对",
}


def occasion_scores_fit(
    scores_top: dict | None,
    scores_bottom: dict | None,
    target_occasion: str | None = None,
) -> float:
    """V2 场合适配：基于 occasion_scores 评分制。

    参数:
        scores_top: 上装 occasion_scores {"office": 2, "date": 5, ...}
        scores_bottom: 下装 occasion_scores
        target_occasion: 目标场景（如 "date"），None 时计算整体相似度
    返回: [0.0, 1.0]
    """
    if not scores_top or not scores_bottom:
        return 0.5

    # 指定场景：取该场景评分均值 (1-5 → 0.2-1.0)
    if target_occasion and target_occasion in scores_top and target_occasion in scores_bottom:
        avg = (scores_top[target_occasion] + scores_bottom[target_occasion]) / 2.0
        return max(0.0, min(1.0, avg / 5.0))

    # 未指定场景：计算所有场景的余弦相似度
    keys = set(scores_top.keys()) & set(scores_bottom.keys())
    if not keys:
        return 0.5
    a = np.array([scores_top[k] for k in keys], dtype=np.float32)
    b = np.array([scores_bottom[k] for k in keys], dtype=np.float32)
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na > 0 and nb > 0:
        return (float(np.dot(a, b) / (na * nb)) + 1) / 2
    return 0.5
