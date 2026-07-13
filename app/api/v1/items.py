from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, File, Query, Request, UploadFile

from app.core.config import settings
from app.core.exceptions import AIException, BadRequestException, NotFoundException
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.item import (
    BatchImportItemResult,
    BatchImportResponse,
    BatchImportStatusResponse,
    ItemCreate,
    ItemListResponse,
    ItemOut,
    ItemUpdate,
    WearRecordResponse,
)
from app.services.ai.feature_extraction import enqueue_extraction
from app.services.batch_import_service import batch_import, get_batch_status
from app.services.image_util import validate_image
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
    tags: Annotated[list[str] | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    sort: Annotated[str | None, Query()] = None,
):
    # 兼容 wx.request 将数组序列化为逗号分隔字符串的情况
    normalized_tags: list[str] | None = None
    if tags:
        normalized_tags = []
        for t in tags:
            normalized_tags.extend([s.strip() for s in t.split(",") if s.strip()])
        if not normalized_tags:
            normalized_tags = None
    items = await list_items(
        db=db,
        user_id=UUID(user_id),
        category=category,
        tag=tag,
        tags=normalized_tags,
        search=search,
        sort=sort,
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
    background_tasks: BackgroundTasks,
):
    item = await create_item(
        db=db,
        user_id=UUID(user_id),
        data=body,
        base_url=str(request.base_url),
    )
    # 触发异步特征提取（MLLM 属性 + 视觉向量）
    background_tasks.add_task(enqueue_extraction, item.id)
    return success(data=ItemOut.model_validate(item).model_dump(by_alias=True))


# ---------- 批量导入 ----------


@router.post("/batch-import")
async def batch_import_items(
    files: list[UploadFile] = File(...),
    db: DbSession,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
):
    """批量上传衣物图片 -> HighwayAPI 衣物提取 -> COS 保存 -> 创建 Item -> 后台属性提取。

    每张图片独立处理：提取失败则创建 failed Item 并保留原图。
    """
    if not files:
        raise BadRequestException("请至少上传一张图片")
    if len(files) > settings.batch_import_max_files:
        raise BadRequestException(f"单次最多上传 {settings.batch_import_max_files} 张图片")

    # 校验所有图片
    validated: list[tuple[bytes, str, str]] = []
    for file in files:
        suffix, content = validate_image(file)
        ext = suffix.lstrip(".")
        mime_ext = "jpeg" if ext == "jpg" else ext
        content_type = f"image/{mime_ext}"
        validated.append((content, ext, content_type))

    # 批量处理
    batch, results = await batch_import(
        db=db,
        user_id=UUID(user_id),
        files=validated,
        background_tasks=background_tasks,
    )

    return success(
        data=BatchImportResponse(
            batch_id=batch.id,
            status=batch.status,
            total=batch.total_count,
            success=batch.success_count,
            failed=batch.failed_count,
            items=[
                BatchImportItemResult(
                    status=r["status"],
                    item_id=r.get("item_id"),
                    image_url=r.get("image_url"),
                    error=r.get("error"),
                )
                for r in results
            ],
        ).model_dump(by_alias=True)
    )


@router.get("/batch-import/{batch_id}")
async def get_batch_import_status_endpoint(
    batch_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    """查询批量导入任务状态。"""
    result = await get_batch_status(db=db, user_id=UUID(user_id), batch_id=batch_id)
    return success(
        data=BatchImportStatusResponse(
            batch_id=result["batch_id"],
            status=result["status"],
            total=result["total"],
            success=result["success"],
            failed=result["failed"],
            created_at=result["created_at"],
            items=[ItemOut.model_validate(item) for item in result["items"]],
        ).model_dump(by_alias=True)
    )


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
    request: Request,
):
    item = await update_item(
        db=db,
        user_id=UUID(user_id),
        item_id=item_id,
        data=body,
        base_url=str(request.base_url),
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


@router.post("/{item_id}/retry-extract")
async def retry_extract(
    item_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
    background_tasks: BackgroundTasks,
):
    """手动重试单品的特征提取（用于失败恢复）。"""
    item = await get_item(db=db, user_id=UUID(user_id), item_id=item_id)
    background_tasks.add_task(enqueue_extraction, item.id)
    return success(data={"status": "queued"})
