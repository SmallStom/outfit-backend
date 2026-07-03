"""五维打分纯函数：Style / Color / Occasion / Weather / User_Bias。

所有函数返回 [0.0, 1.0] 之间的浮点分数。
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
