from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.favorite import (
    FavoriteItemOut,
    FavoritePostOut,
    FavoriteTryonResultOut,
    FavoritesResponse,
)
from app.services.favorite_service import (
    is_tryon_result_favorited,
    list_favorites,
    toggle_favorite_item,
    toggle_favorite_post,
    toggle_favorite_tryon_result,
)

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("")
async def get_favorites(db: DbSession, user_id: CurrentUserId):
    data = await list_favorites(db=db, user_id=UUID(user_id))
    return success(
        data=FavoritesResponse(
            posts=[
                FavoritePostOut.model_validate(row).model_dump(by_alias=True)
                for row in data["posts"]
            ],
            items=[
                FavoriteItemOut.model_validate(row).model_dump(by_alias=True)
                for row in data["items"]
            ],
            tryon_results=[
                FavoriteTryonResultOut.model_validate(row).model_dump(by_alias=True)
                for row in data["tryon_results"]
            ],
        ).model_dump(by_alias=True)
    )


@router.get("/tryon-results/{tryon_result_id}/is-favorited")
async def get_tryon_result_is_favorited(
    tryon_result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    is_favorited = await is_tryon_result_favorited(
        db=db, user_id=UUID(user_id), tryon_result_id=tryon_result_id
    )
    return success(data={"isFavorited": is_favorited})


@router.post("/posts/{post_id}")
async def favorite_post(
    post_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await toggle_favorite_post(db=db, user_id=UUID(user_id), post_id=post_id)
    return success(data={"success": True})


@router.post("/items/{item_id}")
async def favorite_item(
    item_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await toggle_favorite_item(db=db, user_id=UUID(user_id), item_id=item_id)
    return success(data={"success": True})


@router.post("/tryon-results/{tryon_result_id}")
async def favorite_tryon_result(
    tryon_result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    is_favorited = await toggle_favorite_tryon_result(
        db=db, user_id=UUID(user_id), tryon_result_id=tryon_result_id
    )
    return success(data={"isFavorited": is_favorited})
