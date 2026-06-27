from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.outfit import (
    OutfitCollectionCreate,
    OutfitCollectionListResponse,
    OutfitCollectionOut,
    OutfitCollectionUpdate,
    OutfitCreate,
    OutfitListResponse,
    OutfitOut,
    OutfitUpdate,
)
from app.services.outfit_service import (
    create_collection,
    create_outfit,
    delete_collection,
    delete_outfit,
    get_collection,
    get_outfit,
    list_collections,
    list_outfits,
    recommend_outfit,
    update_collection,
    update_outfit,
)
from app.services.outfit_service import _item_entry

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


@outfits_router.get("/recommend")
async def recommend(db: DbSession, user_id: CurrentUserId):
    outfit = await recommend_outfit(db=db, user_id=UUID(user_id))
    return success(data=_outfit_out(outfit).model_dump(by_alias=True))


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
