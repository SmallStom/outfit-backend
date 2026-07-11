from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.rate_limiter import check_rate_limit
from app.core.exceptions import BadRequestException
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.models.shop_item import ShopItem
from app.schemas.outfit import (
    DailyRecommendResponse,
    FeedbackCreate,
    OutfitCollectionCreate,
    OutfitCollectionListResponse,
    OutfitCollectionOut,
    OutfitCollectionUpdate,
    OutfitCreate,
    OutfitItemEntry,
    OutfitListResponse,
    OutfitOut,
    OutfitUpdate,
    ShopOutfitOut,
    WeatherInfo,
)
from app.services.ai.weather_service import get_weather
from app.services.outfit_service import (
    create_collection,
    create_outfit,
    delete_collection,
    delete_outfit,
    get_collection,
    get_outfit,
    list_collections,
    list_outfits,
    record_feedback,
    recommend_daily,
    update_collection,
    update_outfit,
)
from app.services.outfit_service import _item_entry
from app.services.tryon_service import (
    generate_tryon,
    get_tryon_result,
    refresh_tryon_result,
)
from app.schemas.tryon import OutfitTryonRequest, TryonResultOut
from app.services.reco import shop_recommender
from app.services.reco.engine import _build_item_description
from app.services.ai.dashscope_client import dashscope_client, sanitize_prompt_text
from app.core.prompts import REASON_GENERATION_PROMPT
from app.core.config import settings

outfits_router = APIRouter(prefix="/outfits", tags=["outfits"])
collections_router = APIRouter(prefix="/outfit-collections", tags=["outfit-collections"])


def _outfit_out(outfit) -> OutfitOut:
    return OutfitOut(
        id=outfit.id,
        name=outfit.name,
        cover_url=outfit.cover_url,
        cover_color=outfit.cover_color,
        occasion=outfit.occasion,
        weather=outfit.weather,
        is_ai_generated=outfit.is_ai_generated,
        color_scheme=outfit.color_scheme,
        items=[_item_entry(oi.item) for oi in outfit.items],
        reason=outfit.reason,
        score=outfit.score,
        temperature=outfit.temperature,
        created_at=outfit.created_at,
        updated_at=outfit.updated_at,
    )


def _collection_out(collection) -> OutfitCollectionOut:
    return OutfitCollectionOut(
        id=collection.id,
        name=collection.name,
        desc=collection.desc,
        cover_url=collection.cover_url,
        cover_color=collection.cover_color,
        count=len(collection.items),
        items=[_item_entry(ci.item) for ci in collection.items],
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def _shop_item_entry(item: ShopItem) -> OutfitItemEntry:
    return OutfitItemEntry(
        id=item.id,
        name=item.name,
        category=item.category,
        image_url=item.image_url or "",
        image_color=item.image_color,
        thumbnail_url=item.thumbnail_url,
        price=item.price,
        source_url=item.source_url,
        is_shop_item=True,
    )


def _shop_outfit_out(combo: dict) -> ShopOutfitOut:
    return ShopOutfitOut(
        id=combo["id"],
        name=combo["name"],
        cover_url=combo["cover_url"],
        cover_color=combo["cover_color"],
        weather=combo["weather"],
        is_ai_generated=False,
        reason=combo["reason"],
        score=combo["score"],
        temperature=combo["temperature"],
        items=[_shop_item_entry(i) for i in combo["items"]],
    )


@outfits_router.get("/recommend")
async def recommend(
    db: DbSession,
    user_id: CurrentUserId,
    lng: Annotated[float | None, Query()] = None,
    lat: Annotated[float | None, Query()] = None,
    city: Annotated[str | None, Query()] = None,
    refresh: Annotated[bool, Query()] = False,
):
    # 限流：防止 refresh=true 反复触发 LLM/天气 API 导致费用暴涨
    check_rate_limit(user_id, "outfits:recommend")
    weather = await get_weather(lng=lng, lat=lat, city=city)
    wardrobe_outfits = await recommend_daily(
        db=db,
        user_id=UUID(user_id),
        weather=weather,
        force_refresh=refresh,
    )
    shop_combos = await shop_recommender.recommend_shop_outfits(
        db=db,
        user_id=UUID(user_id),
        weather=weather,
    )
    payload = DailyRecommendResponse(
        list=[_outfit_out(o) for o in wardrobe_outfits],
        shop=[_shop_outfit_out(c) for c in shop_combos],
        weather=WeatherInfo(**weather.to_dict()),
    )
    return success(data=payload.model_dump(by_alias=True))


@outfits_router.get("")
async def get_outfits(
    db: DbSession,
    user_id: CurrentUserId,
    ai_only: bool | None = Query(default=None),
):
    outfits = await list_outfits(db=db, user_id=UUID(user_id), ai_only=ai_only)
    return success(
        data=OutfitListResponse(
            list=[_outfit_out(o) for o in outfits],
            total=len(outfits),
        ).model_dump(by_alias=True)
    )


@outfits_router.post("")
async def create_new_outfit(
    body: OutfitCreate,
    db: DbSession,
    user_id: CurrentUserId,
):
    outfit = await create_outfit(db=db, user_id=UUID(user_id), data=body)
    return success(data=_outfit_out(outfit).model_dump(by_alias=True))


@outfits_router.get("/{outfit_id}")
async def get_outfit_detail(
    outfit_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    outfit = await get_outfit(db=db, user_id=UUID(user_id), outfit_id=outfit_id)
    return success(data=_outfit_out(outfit).model_dump(by_alias=True))


@outfits_router.put("/{outfit_id}")
async def update_existing_outfit(
    outfit_id: UUID,
    body: OutfitUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    outfit = await update_outfit(
        db=db, user_id=UUID(user_id), outfit_id=outfit_id, data=body
    )
    return success(data=_outfit_out(outfit).model_dump(by_alias=True))


@outfits_router.delete("/{outfit_id}")
async def remove_outfit(
    outfit_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await delete_outfit(db=db, user_id=UUID(user_id), outfit_id=outfit_id)
    return success()


@outfits_router.post("/{outfit_id}/feedback")
async def submit_feedback(
    outfit_id: UUID,
    body: FeedbackCreate,
    db: DbSession,
    user_id: CurrentUserId,
):
    await record_feedback(
        db=db,
        user_id=UUID(user_id),
        outfit_id=outfit_id,
        action=body.action,
        item_id=body.item_id,
    )
    return success()


@outfits_router.post("/{outfit_id}/reason")
async def generate_reason(
    outfit_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    """V2: 生成详细推荐理由（含 V2 属性分析）。"""
    outfit = await get_outfit(db=db, user_id=UUID(user_id), outfit_id=outfit_id)

    if not settings.ai_api_key:
        return success(data={"reason": outfit.reason or "暂无推荐理由"})

    items = [oi.item for oi in outfit.items]
    top = next((i for i in items if i.category == "top"), items[0] if items else None)
    bottom = next((i for i in items if i.category in ("bottom", "dress")), items[-1] if len(items) > 1 else None)

    if not top or not bottom:
        return success(data={"reason": outfit.reason or "暂无推荐理由"})

    # 构建用户 prompt
    lines = [
        f"天气：{outfit.weather or '未知'}",
        f"场合：{outfit.occasion or '日常'}",
        "",
        f"上装：{sanitize_prompt_text(top.name, max_len=25)}，{_build_item_description(top)}",
        f"下装：{sanitize_prompt_text(bottom.name, max_len=25)}，{_build_item_description(bottom)}",
    ]
    user_prompt = "\n".join(lines)

    try:
        payload = {
            "model": settings.ai_rerank_model,
            "messages": [
                {"role": "system", "content": REASON_GENERATION_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
        }
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{settings.ai_dashscope_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.ai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
        reason = data["choices"][0]["message"]["content"].strip()
        if reason:
            outfit.reason = reason[:200]
            await db.commit()
        return success(data={"reason": reason or outfit.reason or "暂无推荐理由"})
    except Exception:
        return success(data={"reason": outfit.reason or "暂无推荐理由"})


@outfits_router.post("/{outfit_id}/tryon")
async def tryon_outfit(
    outfit_id: UUID,
    body: OutfitTryonRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    """Phase 7: 推荐搭配一键试穿。

    自动选取 outfit 中的上装 + 下装，调用试穿服务生成真人试穿图，
    结果保存到 tryon_results 表并返回试穿结果 URL。
    """
    outfit = await get_outfit(db=db, user_id=UUID(user_id), outfit_id=outfit_id)
    items = [oi.item for oi in outfit.items]

    top_item = next((i for i in items if i.category in ("top", "outer")), None)
    bottom_item = next(
        (i for i in items if i.category in ("bottom", "dress")), None
    )
    if not top_item and not bottom_item:
        raise BadRequestException("该搭配中没有可试穿的上装或下装")

    result = await generate_tryon(
        db=db,
        user_id=UUID(user_id),
        mode="fast",
        person_image_url=body.person_image,
        top_item_id=top_item.id if top_item else None,
        bottom_item_id=bottom_item.id if bottom_item else None,
    )
    tryon_result = await get_tryon_result(
        db=db, user_id=UUID(user_id), result_id=result["id"]
    )
    tryon_result = await refresh_tryon_result(db=db, tryon_result=tryon_result)
    return success(
        data=TryonResultOut.model_validate(tryon_result).model_dump(by_alias=True)
    )


@collections_router.get("")
async def get_collections(db: DbSession, user_id: CurrentUserId):
    collections = await list_collections(db=db, user_id=UUID(user_id))
    return success(
        data=OutfitCollectionListResponse(
            list=[_collection_out(c) for c in collections],
            total=len(collections),
        ).model_dump(by_alias=True)
    )


@collections_router.post("")
async def create_new_collection(
    body: OutfitCollectionCreate,
    db: DbSession,
    user_id: CurrentUserId,
):
    collection = await create_collection(
        db=db, user_id=UUID(user_id), data=body
    )
    return success(data=_collection_out(collection).model_dump(by_alias=True))


@collections_router.get("/{collection_id}")
async def get_collection_detail(
    collection_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    collection = await get_collection(
        db=db, user_id=UUID(user_id), collection_id=collection_id
    )
    return success(data=_collection_out(collection).model_dump(by_alias=True))


@collections_router.put("/{collection_id}")
async def update_existing_collection(
    collection_id: UUID,
    body: OutfitCollectionUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    collection = await update_collection(
        db=db, user_id=UUID(user_id), collection_id=collection_id, data=body
    )
    return success(data=_collection_out(collection).model_dump(by_alias=True))


@collections_router.delete("/{collection_id}")
async def remove_collection(
    collection_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await delete_collection(
        db=db, user_id=UUID(user_id), collection_id=collection_id
    )
    return success()
