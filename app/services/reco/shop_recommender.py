"""外部好物推荐器。

基于用户角色（性别 + 体型 + 衣橱风格推断）与商品元数据的规则匹配算法。
不调用任何 AI 服务，不依赖向量 Embedding。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.body_profile import BodyProfile
from app.models.item import Item
from app.models.shop_item import ShopItem
from app.models.user import User
from app.services.ai.weather_service import WeatherResult

logger = logging.getLogger(__name__)

# ---------- 风格画像关键词词典 ----------
PERSONA_KEYWORDS: dict[str, set[str]] = {
    "commute": {"西装", "衬衫", "西裤", "直筒裤", "百褶", "针织", "POLO", "利落", "通勤"},
    "casual": {"TEE", "T恤", "圆领", "短裤", "牛仔裤", "休闲", "基础", "纯棉"},
    "street": {"印花", "宽版", "背心", "刷破", "绑腰", "动物印", "扎染", "个性"},
    "feminine": {"洋装", "蕾丝", "喇叭裤", "短裙", "飘逸", "显瘦", "约会"},
    "sporty": {"凉感", "冰感", "排汗", "运动", "背心", "锥形裤", "机能"},
    "minimal": {"圆领", "基本", "纯色", "简约", "百搭", "纯棉", "TEE"},
}

PERSONA_LABELS: dict[str, str] = {
    "commute": "职场通勤",
    "casual": "日常休闲",
    "street": "潮流街头",
    "feminine": "温柔甜美",
    "sporty": "运动休闲",
    "minimal": "简约基础",
}

# ---------- 体型适配规则 ----------
BODY_TYPE_RULES: dict[str, dict[str, Any]] = {
    "梨形": {
        "boost": {"高腰", "A字", "喇叭", "百褶", "短裙", "阔腿"},
        "avoid": {"紧身", "铅笔", "包臀"},
        "default": 0.5,
    },
    "苹果型": {
        "boost": {"宽松", "直筒", "锥形", "落肩", "长款"},
        "avoid": {"紧身", "短款", "收腰", "露脐"},
        "default": 0.5,
    },
    "倒三角型": {
        "boost": {"阔腿", "喇叭", "A字", "百褶", "短裙"},
        "avoid": {"垫肩", "夸张", "泡泡袖"},
        "default": 0.5,
    },
    "直筒型": {
        "boost": {"绑腰", "腰带式", "收腰", "A字", "高腰"},
        "avoid": {"直筒裙", "H型", "无腰线"},
        "default": 0.5,
    },
    "标准型": {
        "boost": set(),
        "avoid": set(),
        "default": 0.7,
    },
}

# 体型 key -> label 兜底映射（当只有 key 时）
BODY_KEY_TO_LABEL: dict[str, str] = {
    "standard": "标准型",
    "inverted-triangle": "倒三角型",
    "pear": "梨形",
    "apple": "苹果型",
    "rectangle": "直筒型",
}

# ---------- 天气/季节关键词 ----------
SUMMER_HINTS = {"凉感", "冰感", "轻薄", "短袖", "短裤", "背心", "夏季", "夏天", "透气"}
WINTER_HINTS = {"长袖", "针织", "厚", "毛呢", "呢", "绒", "冬季", "冬天", "保暖"}
RAIN_SENSITIVE = {"丝", "silk", "毛呢", "呢"}

# ---------- 性别推断 ----------
FEMALE_HINTS = {"洋装", "蕾丝", "短裙", "裙", "吊带", "一字领", "荷叶"}
MALE_HINTS = {"男装", "男士", "男款"}

# ---------- 风格平衡 ----------
LOUD_HINTS = {"印花", "动物印", "扎染", "图案", "撞色", "亮色"}
BASIC_HINTS = {"纯色", "基础", "TEE", "T恤", "圆领", "纯棉"}


@dataclass
class UserRole:
    gender: str | None = None
    body_type: str | None = None
    style_persona: str = "casual"


@dataclass
class ShopItemTags:
    style_tags: set[str] = field(default_factory=set)
    raw_style_tags: set[str] = field(default_factory=set)
    body_hints: set[str] = field(default_factory=set)
    weather_hints: set[str] = field(default_factory=set)
    gender_hint: str = "unisex"


def _normalize_body_type(body_type: str | None, body_type_label: str | None) -> str | None:
    """统一体型为中文 label。"""
    if body_type_label:
        return body_type_label
    if body_type and body_type in BODY_KEY_TO_LABEL:
        return BODY_KEY_TO_LABEL[body_type]
    return None


def _collect_text(*parts: Any) -> str:
    """把多个字段拼接成一段小写文本，用于关键词匹配。"""
    texts: list[str] = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, list):
            texts.extend(str(p) for p in part if p is not None)
        else:
            texts.append(str(part))
    return " ".join(texts).lower()


def _match_keywords(text: str, keywords: set[str]) -> set[str]:
    """返回命中了哪些关键词（子串匹配）。"""
    return {kw for kw in keywords if kw.lower() in text}


def tag_shop_item(item: ShopItem) -> ShopItemTags:
    """根据商品元数据生成规则标签。"""
    text = _collect_text(item.name, item.sub_category, item.description, item.material, item.season)
    tag_text = _collect_text(item.tags)
    full_text = f"{text} {tag_text}"

    style_tags: set[str] = set()
    for persona, kws in PERSONA_KEYWORDS.items():
        if _match_keywords(full_text, kws):
            style_tags.add(persona)

    raw_style_tags = _match_keywords(full_text, LOUD_HINTS | BASIC_HINTS)

    body_hints = _match_keywords(full_text, {
        "高腰", "A字", "宽松", "直筒", "绑腰", "腰带式", "喇叭", "收腰",
        "短裙", "短裤", "洋装", "锥形", "阔腿", "落肩", "长款", "短款",
        "紧身", "铅笔", "包臀", "垫肩", "泡泡袖", "一字领", "荷叶",
        "H型", "无腰线", "直筒裙", "夸张",
    })

    weather_hints = _match_keywords(full_text, SUMMER_HINTS | WINTER_HINTS)

    gender_hint = "unisex"
    if _match_keywords(full_text, FEMALE_HINTS):
        gender_hint = "female"
    elif _match_keywords(full_text, MALE_HINTS):
        gender_hint = "male"

    return ShopItemTags(
        style_tags=style_tags,
        raw_style_tags=raw_style_tags,
        body_hints=body_hints,
        weather_hints=weather_hints,
        gender_hint=gender_hint,
    )


def _score_style(tags: ShopItemTags, role: UserRole) -> float:
    """风格匹配分：商品风格标签与用户画像的重叠程度。"""
    persona = role.style_persona
    if persona not in PERSONA_KEYWORDS:
        return 0.5
    if not tags.style_tags:
        return 0.3
    return 1.0 if persona in tags.style_tags else 0.3


def _score_body(tags: ShopItemTags, role: UserRole) -> float:
    """体型适配分。"""
    body_type = role.body_type
    if not body_type or body_type not in BODY_TYPE_RULES:
        return 0.6
    rule = BODY_TYPE_RULES[body_type]
    score = rule["default"]
    boost_hits = len(tags.body_hints & rule["boost"])
    avoid_hits = len(tags.body_hints & rule["avoid"])
    score += 0.15 * boost_hits
    score -= 0.15 * avoid_hits
    return max(0.0, min(1.0, score))


def _score_weather(tags: ShopItemTags, weather: WeatherResult) -> float:
    """天气适配分。"""
    temp = weather.temperature
    hints = tags.weather_hints

    # 基础季节分
    if temp >= 25:
        if hints & SUMMER_HINTS:
            return 1.0
        if hints & WINTER_HINTS:
            return 0.3
    elif temp <= 15:
        if hints & WINTER_HINTS:
            return 1.0
        if hints & SUMMER_HINTS:
            return 0.3
    else:
        # 春秋过渡季：有明确季节属性不低于无属性
        if not hints:
            return 0.7
        has_summer = bool(hints & SUMMER_HINTS)
        has_winter = bool(hints & WINTER_HINTS)
        if has_summer and has_winter:
            return 0.85
        if has_summer or has_winter:
            return 0.8

    return 0.6


def _score_gender(tags: ShopItemTags, role: UserRole) -> float:
    """性别匹配分。"""
    gender = (role.gender or "").lower()
    hint = tags.gender_hint
    if gender in ("", "unknown"):
        return 0.8
    if gender == "female":
        return 1.0 if hint == "female" else (0.6 if hint == "unisex" else 0.3)
    if gender == "male":
        return 1.0 if hint == "male" else (0.6 if hint == "unisex" else 0.3)
    return 0.8


def _score_balance(top_tags: ShopItemTags, bottom_tags: ShopItemTags) -> float:
    """组合平衡分：一花一素更协调。"""
    top_loud = bool(top_tags.raw_style_tags & LOUD_HINTS or top_tags.body_hints & LOUD_HINTS)
    bot_loud = bool(bottom_tags.raw_style_tags & LOUD_HINTS or bottom_tags.body_hints & LOUD_HINTS)
    top_basic = bool(top_tags.raw_style_tags & BASIC_HINTS or top_tags.body_hints & BASIC_HINTS)
    bot_basic = bool(bottom_tags.raw_style_tags & BASIC_HINTS or bottom_tags.body_hints & BASIC_HINTS)

    if top_loud and bot_loud:
        return 0.4
    if top_loud and bot_basic:
        return 1.0
    if top_basic and bot_loud:
        return 1.0
    if top_basic and bot_basic:
        return 0.7
    return 0.75


def _total_score(
    top_tags: ShopItemTags,
    bottom_tags: ShopItemTags,
    role: UserRole,
    weather: WeatherResult,
) -> float:
    """加权总分。"""
    style = (_score_style(top_tags, role) + _score_style(bottom_tags, role)) / 2.0
    body = (_score_body(top_tags, role) + _score_body(bottom_tags, role)) / 2.0
    weather_score = (_score_weather(top_tags, weather) + _score_weather(bottom_tags, weather)) / 2.0
    gender = (_score_gender(top_tags, role) + _score_gender(bottom_tags, role)) / 2.0
    balance = _score_balance(top_tags, bottom_tags)
    return 0.30 * style + 0.25 * body + 0.20 * weather_score + 0.10 * gender + 0.15 * balance


def _pass_hard_filter(item: ShopItem, tags: ShopItemTags, weather: WeatherResult) -> bool:
    """硬过滤：雨雪天和温度极端不匹配。"""
    text = _collect_text(item.name, item.sub_category, item.description, item.material, item.season, item.tags)
    weather_text = weather.text or ""

    # 雨雪天剔除易损材质
    if any(w in weather_text for w in ("雨", "雪")):
        if any(k in text for k in RAIN_SENSITIVE):
            return False

    temp = weather.temperature
    hints = tags.weather_hints

    # 冬季排除明显夏装
    if temp < 10 and hints & SUMMER_HINTS and not (hints & WINTER_HINTS):
        return False
    # 夏季排除明显冬装
    if temp > 30 and hints & WINTER_HINTS and not (hints & SUMMER_HINTS):
        return False

    return True


async def infer_user_role(db: AsyncSession, user_id: UUID) -> UserRole:
    """推断用户角色。"""
    # 性别与体型
    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    gender = (user.gender or "").lower() if user else None

    body_result = await db.execute(
        select(BodyProfile)
        .where(BodyProfile.user_id == user_id, BodyProfile.is_active.is_(True))
    )
    profile = body_result.scalar_one_or_none()
    body_type = _normalize_body_type(
        profile.body_type if profile else None,
        profile.body_type_label if profile else None,
    )

    # 衣橱风格推断
    item_result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    items = list(item_result.scalars().all())

    persona_scores: dict[str, int] = {k: 0 for k in PERSONA_KEYWORDS}
    for item in items:
        text = _collect_text(item.name, item.sub_category, item.description, item.material, item.tags)
        for persona, kws in PERSONA_KEYWORDS.items():
            persona_scores[persona] += len(_match_keywords(text, kws))

    if persona_scores and max(persona_scores.values()) > 0:
        style_persona = max(persona_scores, key=persona_scores.get)
    else:
        # 无衣橱数据时按性别/体型兜底
        if gender == "female" and body_type in {"梨形", "苹果型", "直筒型"}:
            style_persona = "feminine"
        elif gender == "male":
            style_persona = "minimal"
        else:
            style_persona = "casual"

    return UserRole(gender=gender, body_type=body_type, style_persona=style_persona)


def _build_reason(
    top: ShopItem,
    bottom: ShopItem,
    top_tags: ShopItemTags,
    bottom_tags: ShopItemTags,
    role: UserRole,
    weather: WeatherResult,
) -> str:
    """根据最高维度生成推荐理由。"""
    style = (_score_style(top_tags, role) + _score_style(bottom_tags, role)) / 2.0
    body = (_score_body(top_tags, role) + _score_body(bottom_tags, role)) / 2.0
    weather_score = (_score_weather(top_tags, weather) + _score_weather(bottom_tags, weather)) / 2.0

    scores = {
        "body": body,
        "weather": weather_score,
        "style": style,
    }
    dim = max(scores, key=scores.get)

    if dim == "body" and role.body_type:
        return f"根据你的{role.body_type}身材，推荐这套搭配，修饰身形比例"
    if dim == "weather":
        temp = weather.temperature
        if temp >= 28:
            return f"当前{weather.text} {int(round(temp))}°C，这套透气凉爽"
        if temp <= 12:
            return f"当前{weather.text} {int(round(temp))}°C，这套保暖实用"
        return f"当前{weather.text} {int(round(temp))}°C，这套穿着舒适"
    if dim == "style":
        return f"{PERSONA_LABELS.get(role.style_persona, '日常')}风格，符合你的偏好"
    return "经典基础搭配，不易出错"


async def recommend_shop_outfits(
    db: AsyncSession,
    user_id: UUID,
    weather: WeatherResult,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """为指定用户生成外部好物推荐。"""
    top_n = top_n or settings.reco_shop_top_k

    role = await infer_user_role(db, user_id)

    # 加载全部可用外部商品
    result = await db.execute(
        select(ShopItem).where(
            ShopItem.is_enabled.is_(True),
        )
    )
    all_items = list(result.scalars().all())

    # 标签化 + 硬过滤
    all_tagged = [(item, tag_shop_item(item)) for item in all_items]
    tagged_items = [
        (item, tags)
        for item, tags in all_tagged
        if _pass_hard_filter(item, tags, weather)
    ]

    tops = [(i, t) for i, t in tagged_items if i.category == "top"]
    bottoms = [(i, t) for i, t in tagged_items if i.category == "bottom"]
    dresses = [(i, t) for i, t in tagged_items if i.category == "dress"]

    combos: list[dict[str, Any]] = []

    # top + bottom
    for top, top_tags in tops:
        for bottom, bottom_tags in bottoms:
            score = _total_score(top_tags, bottom_tags, role, weather)
            combos.append({
                "items": [top, bottom],
                "tags": [top_tags, bottom_tags],
                "score": score,
            })

    # top + dress
    for top, top_tags in tops:
        for dress, dress_tags in dresses:
            score = _total_score(top_tags, dress_tags, role, weather)
            combos.append({
                "items": [top, dress],
                "tags": [top_tags, dress_tags],
                "score": score,
            })

    # dress 单件
    for dress, dress_tags in dresses:
        # 单件时平衡分按基础分处理
        score = (
            0.30 * _score_style(dress_tags, role)
            + 0.25 * _score_body(dress_tags, role)
            + 0.20 * _score_weather(dress_tags, weather)
            + 0.10 * _score_gender(dress_tags, role)
            + 0.15 * 0.7
        )
        combos.append({
            "items": [dress],
            "tags": [dress_tags],
            "score": score,
        })

    if not combos:
        return []

    combos.sort(key=lambda x: x["score"], reverse=True)

    # 多样性：同一件单品最多出现 2 次
    item_counts: dict[UUID, int] = {}
    selected: list[dict[str, Any]] = []
    for combo in combos:
        if all(item_counts.get(item.id, 0) < 2 for item in combo["items"]):
            for item in combo["items"]:
                item_counts[item.id] = item_counts.get(item.id, 0) + 1
            selected.append(combo)
        if len(selected) >= top_n:
            break

    # 组装返回结构
    results: list[dict[str, Any]] = []
    for combo in selected:
        items = combo["items"]
        tags = combo["tags"]
        score = combo["score"]
        if len(items) == 2:
            top, bottom = items[0], items[1]
            top_tags, bottom_tags = tags[0], tags[1]
            reason = _build_reason(top, bottom, top_tags, bottom_tags, role, weather)
            name = f"{top.name} × {bottom.name}"
            cover_url = top.image_url or bottom.image_url
        else:
            item = items[0]
            reason = _build_reason(item, item, tags[0], tags[0], role, weather)
            name = item.name
            cover_url = item.image_url

        results.append({
            "id": f"shop-{'-'.join(str(i.id) for i in items)}",
            "name": name[:60],
            "cover_url": cover_url,
            "cover_color": items[0].image_color,
            "reason": reason,
            "score": round(score, 3),
            "temperature": weather.temperature,
            "weather": f"{weather.text} {int(round(weather.temperature))}°C",
            "items": items,
        })

    return results
