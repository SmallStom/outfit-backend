from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.favorite import (
    FavoriteItemOut,
    FavoritePostOut,
    FavoritesResponse,
)
from app.services.favorite_service import (
    list_favorites,
    toggle_favorite_item,
    toggle_favorite_post,
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
        ).model_dump(by_alias=True)
    )


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
