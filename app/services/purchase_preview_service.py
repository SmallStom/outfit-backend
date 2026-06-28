import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.item import Item
from app.models.purchase_preview import PurchasePreview
from app.schemas.purchase_preview import PurchaseAnalyzeRequest


_DEFAULT_CANDIDATE = {
    "item_name": "亚麻凉感直筒裤",
    "estimated_price": 499,
    "category": "bottom",
    "color": "#f0ece6",
    "image_url": "",
}


def _hash_int(seed: str, max_val: int = 100) -> int:
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max_val


async def _user_items(db: AsyncSession, user_id: UUID) -> list[Item]:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


def _analyze_candidate(
    candidate: dict, items: list[Item]
) -> dict:
    name = candidate["item_name"]
    price = candidate["estimated_price"]
    category = candidate["category"]
    color = candidate["color"]

    similar_items = sum(
        1
        for item in items
        if item.category == category or item.color == color
    )

    base_match = 65 + _hash_int(f"{name}:match", 25)
    if similar_items > 5:
        base_match -= 5
    match_rate = max(55, min(95, base_match))

    suggested_count = 10 + _hash_int(f"{name}:count", 8)
    cost_per_wear = int(price / suggested_count) if suggested_count else 0

    details = {
        "color_match": max(60, min(98, match_rate + _hash_int(f"{name}:color", 11) - 5)),
        "style_match": max(60, min(98, match_rate + _hash_int(f"{name}:style", 11) - 8)),
        "season_match": max(60, min(98, match_rate + _hash_int(f"{name}:season", 11) - 2)),
        "occasion_match": max(60, min(98, match_rate + _hash_int(f"{name}:occasion", 11) - 10)),
    }

    if match_rate >= 80:
        hint = "这件单品与您衣橱的匹配度极高，推荐购买"
        status = "analyzed"
    elif match_rate >= 60:
        hint = "匹配度尚可，建议结合自身穿搭频率再决定"
        status = "considering"
    else:
        hint = "与现有衣橱风格/颜色重复度较高，建议谨慎购买"
        status = "passed"

    # 推荐搭配：优先选不同分类、穿着次数高的单品
    suggestion_pool = sorted(
        [item for item in items if item.category != category],
        key=lambda x: x.wear_count or 0,
        reverse=True,
    )[:5]
    if len(suggestion_pool) < 5:
        suggestion_pool += [item for item in items if item.category == category][: 5 - len(suggestion_pool)]

    suggestions = []
    for idx, item in enumerate(suggestion_pool[:5]):
        score = max(70, min(98, 85 + _hash_int(f"{name}:{item.id}:score", 21) - 10))
        suggestions.append(
            {
                "id": item.id,
                "name": item.name,
                "image_color": item.image_color,
                "image_url": item.image_url or "",
                "match_score": score,
            }
        )

    return {
        "item_name": name,
        "estimated_price": price,
        "match_rate": match_rate,
        "suggested_count": suggested_count,
        "cost_per_wear": cost_per_wear,
        "status": status,
        "hint": hint,
        "thumbnail_color": color,
        "image_url": candidate["image_url"],
        "match_details": details,
        "similar_items": similar_items,
        "suggestions": suggestions,
    }


async def analyze(
    db: AsyncSession, user_id: UUID, data: PurchaseAnalyzeRequest
) -> PurchasePreview:
    items = await _user_items(db, user_id)
    candidate = {
        "item_name": data.item_name or _DEFAULT_CANDIDATE["item_name"],
        "estimated_price": data.estimated_price or _DEFAULT_CANDIDATE["estimated_price"],
        "category": data.category or _DEFAULT_CANDIDATE["category"],
        "color": data.color or _DEFAULT_CANDIDATE["color"],
        "image_url": data.image_url or _DEFAULT_CANDIDATE["image_url"],
    }
    result = _analyze_candidate(candidate, items)

    record = PurchasePreview(
        user_id=user_id,
        source_type="manual",
        source_url=data.source_url,
        source_image=data.image_url,
        item_name=result["item_name"],
        estimated_price=result["estimated_price"],
        match_rate=result["match_rate"],
        suggested_count=result["suggested_count"],
        cost_per_wear=result["cost_per_wear"],
        status=result["status"],
        hint=result["hint"],
        thumbnail_color=result["thumbnail_color"],
        image_url=result["image_url"],
        match_details=result["match_details"],
        similar_items=result["similar_items"],
        suggestions=result["suggestions"],
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def get_preview(
    db: AsyncSession, user_id: UUID, preview_id: UUID
) -> PurchasePreview:
    result = await db.execute(
        select(PurchasePreview).where(
            PurchasePreview.id == preview_id,
            PurchasePreview.user_id == user_id,
        )
    )
    preview = result.scalar_one_or_none()
    if preview is None:
        from app.core.exceptions import NotFoundException

        raise NotFoundException("分析记录不存在")
    return preview


async def history(db: AsyncSession, user_id: UUID) -> list[PurchasePreview]:
    result = await db.execute(
        select(PurchasePreview)
        .where(PurchasePreview.user_id == user_id)
        .order_by(PurchasePreview.created_at.desc())
    )
    return list(result.scalars().all())
