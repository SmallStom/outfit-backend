from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.tryon import TryonItem, TryonPreset, TryonPresetItem
from app.services.tryon_service import (
    categories,
    generate_presets,
    generate_tryon,
    items_by_category,
)

router = APIRouter(prefix="/tryon", tags=["tryon"])


@router.get("/items")
async def get_items(
    db: DbSession,
    user_id: CurrentUserId,
    category: Annotated[str, Query()],
):
    items = await items_by_category(db=db, user_id=UUID(user_id), category=category)
    return success(
        data=[
            TryonItem(
                id=item.id,
                name=item.name,
                category=item.category,
                color=item.color,
                image_url=item.image_url or "",
            ).model_dump(by_alias=True)
            for item in items
        ]
    )


@router.get("/presets")
async def get_presets(db: DbSession, user_id: CurrentUserId):
    presets = await generate_presets(db=db, user_id=UUID(user_id))
    result = []
    for preset in presets:
        result.append(
            TryonPreset(
                id=preset["id"],
                name=preset["name"],
                occasion=preset["occasion"],
                items=[
                    TryonPresetItem(
                        id=item.id,
                        name=item.name,
                        category=item.category,
                        color=item.color,
                        image_url=item.image_url or "",
                    ).model_dump(by_alias=True)
                    for item in preset["items"]
                ],
            ).model_dump(by_alias=True)
        )
    return success(data=result)


@router.post("/generate")
async def tryon_generate(body: dict):
    await generate_tryon(**body)
