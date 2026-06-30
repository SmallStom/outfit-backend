from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.tryon import (
    TryonGenerateRequest,
    TryonGenerateResponse,
    TryonItem,
    TryonPreset,
    TryonPresetItem,
    TryonResultOut,
)
from app.services.quota_service import get_quota_summary
from app.services.share_service import share_tryon_result
from app.services.tryon_service import (
    categories,
    generate_presets,
    generate_tryon,
    get_tryon_result,
    items_by_category,
    list_tryon_results,
    refresh_tryon_result,
)

router = APIRouter(prefix="/tryon", tags=["tryon"])


@router.get("/quota")
async def get_tryon_quota(db: DbSession, user_id: CurrentUserId):
    summary = await get_quota_summary(db=db, user_id=UUID(user_id))
    return success(data=summary)


@router.get("/categories")
async def get_categories():
    return success(data=categories())


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
async def tryon_generate(
    body: TryonGenerateRequest,
    user_id: CurrentUserId,
    db: DbSession,
):
    result = await generate_tryon(
        db=db,
        user_id=UUID(user_id),
        mode=body.mode,
        person_image_url=body.person_image_url,
        top_item_id=body.top_item_id,
        bottom_item_id=body.bottom_item_id,
        outer_item_id=body.outer_item_id,
    )
    return success(
        data=TryonGenerateResponse.model_validate(result).model_dump(by_alias=True)
    )


@router.get("/results")
async def get_tryon_results(
    db: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    results, total = await list_tryon_results(
        db=db, user_id=UUID(user_id), limit=limit, offset=offset
    )
    return success(
        data={
            "list": [
                TryonResultOut.model_validate(r).model_dump(by_alias=True)
                for r in results
            ],
            "total": total,
        }
    )


@router.get("/results/{result_id}")
async def get_tryon_result_detail(
    result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    tryon_result = await get_tryon_result(db=db, user_id=UUID(user_id), result_id=result_id)
    tryon_result = await refresh_tryon_result(db=db, tryon_result=tryon_result)
    return success(
        data=TryonResultOut.model_validate(tryon_result).model_dump(by_alias=True)
    )


@router.post("/results/{result_id}/share")
async def share_tryon(
    result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
    title: Annotated[str | None, Query(max_length=200)] = None,
):
    post = await share_tryon_result(db=db, user_id=UUID(user_id), tryon_result_id=result_id, title=title)
    return success(data={"post_id": post.id})
