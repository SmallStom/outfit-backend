from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.core.exceptions import AIException
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.item import (
    ItemCreate,
    ItemListResponse,
    ItemOut,
    ItemUpdate,
    WearRecordResponse,
)
from app.services.item_service import (
    COMMON_TAGS,
    create_item,
    delete_item,
    get_item,
    list_items,
    record_wear,
    update_item,
)

router = APIRouter(prefix="/items", tags=["items"])


@router.get("/common-tags")
async def get_common_tags():
    return success(data=COMMON_TAGS)


@router.post("/recognize")
async def recognize_item():
    # W1 占位：AI 识别将在后续接入 LLM
    raise AIException("AI 识别服务尚未配置")


@router.get("")
async def get_items(
    db: DbSession,
    user_id: CurrentUserId,
    category: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
):
    items = await list_items(
        db=db,
        user_id=UUID(user_id),
        category=category,
        tag=tag,
        search=search,
    )
    return success(
        data=ItemListResponse(
            list=[ItemOut.model_validate(item) for item in items],
            total=len(items),
        ).model_dump(by_alias=True)
    )


@router.post("")
async def create_new_item(
    body: ItemCreate,
    db: DbSession,
    user_id: CurrentUserId,
    request: Request,
):
    item = await create_item(
        db=db,
        user_id=UUID(user_id),
        data=body,
        base_url=str(request.base_url),
    )
    return success(data=ItemOut.model_validate(item).model_dump(by_alias=True))


@router.get("/{item_id}")
async def get_item_detail(
    item_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    item = await get_item(db=db, user_id=UUID(user_id), item_id=item_id)
    return success(data=ItemOut.model_validate(item).model_dump(by_alias=True))


@router.put("/{item_id}")
async def update_existing_item(
    item_id: UUID,
    body: ItemUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    item = await update_item(
        db=db, user_id=UUID(user_id), item_id=item_id, data=body
    )
    return success(data=ItemOut.model_validate(item).model_dump(by_alias=True))


@router.delete("/{item_id}")
async def remove_item(
    item_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await delete_item(db=db, user_id=UUID(user_id), item_id=item_id)
    return success()


@router.post("/{item_id}/wear")
async def wear_item(
    item_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    item = await record_wear(db=db, user_id=UUID(user_id), item_id=item_id)
    return success(
        data=WearRecordResponse(
            success=True,
            wear_count=item.wear_count,
            last_worn_at=item.last_worn_at,
        ).model_dump(by_alias=True)
    )
