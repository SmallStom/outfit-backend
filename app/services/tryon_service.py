import httpx
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AIException, BadRequestException, NotFoundException
from app.models.item import Item
from app.models.tryon_preset import TryonPreset
from app.models.tryon_result import TryonResult

_CATEGORIES = [
    {"key": "top", "label": "上装"},
    {"key": "bottom", "label": "下装"},
    {"key": "dress", "label": "裙装"},
    {"key": "outer", "label": "外套"},
    {"key": "shoes", "label": "鞋履"},
    {"key": "acc", "label": "配饰"},
]

_PRESET_RULES = [
    {
        "id": "preset-1",
        "name": "商务通勤",
        "occasion": "通勤",
        "items": {
            "top": 1,
            "bottom": 1,
            "outer": 1,
            "shoes": 1,
            "acc": 1,
        },
    },
    {
        "id": "preset-2",
        "name": "周末休闲",
        "occasion": "休闲",
        "items": {
            "top": 1,
            "bottom": 1,
            "shoes": 1,
        },
    },
    {
        "id": "preset-3",
        "name": "约会优雅",
        "occasion": "约会",
        "items": {
            "top": 1,
            "bottom": 1,
            "outer": 1,
            "shoes": 1,
            "acc": 1,
        },
    },
    {
        "id": "preset-4",
        "name": "街头潮流",
        "occasion": "休闲",
        "items": {
            "top": 1,
            "bottom": 1,
            "shoes": 1,
        },
    },
]


def categories() -> list[dict]:
    return _CATEGORIES


def _pick_item(
    pool: list[Item], category: str, used_ids: set[UUID]
) -> Item | None:
    for item in pool:
        if item.category == category and item.id not in used_ids:
            used_ids.add(item.id)
            return item
    return None


async def items_by_category(
    db: AsyncSession, user_id: UUID, category: str
) -> list[Item]:
    stmt = (
        select(Item)
        .where(
            Item.user_id == user_id,
            Item.category == category,
            Item.is_deleted.is_(False),
        )
        .order_by(Item.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _all_items(db: AsyncSession, user_id: UUID) -> list[Item]:
    result = await db.execute(
        select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


async def generate_presets(
    db: AsyncSession, user_id: UUID
) -> list[dict]:
    items = await _all_items(db, user_id)
    presets = []
    for rule in _PRESET_RULES:
        used_ids: set[UUID] = set()
        preset_items = []
        for category in ["top", "bottom", "dress", "outer", "shoes", "acc"]:
            count = rule["items"].get(category, 0)
            for _ in range(count):
                item = _pick_item(items, category, used_ids)
                if item:
                    preset_items.append(item)
        # 兜底：每个预设至少放一件上装+下装
        if not preset_items:
            for cat in ["top", "bottom"]:
                item = _pick_item(items, cat, used_ids)
                if item:
                    preset_items.append(item)
        presets.append(
            {
                "id": rule["id"],
                "name": rule["name"],
                "occasion": rule["occasion"],
                "items": preset_items,
            }
        )
    return presets


async def list_presets(
    db: AsyncSession, user_id: UUID
) -> list[TryonPreset]:
    result = await db.execute(
        select(TryonPreset).where(
            (TryonPreset.user_id == user_id) | (TryonPreset.user_id.is_(None))
        )
    )
    return list(result.scalars().all())


async def _get_items(
    db: AsyncSession, user_id: UUID, item_ids: list[UUID]
) -> list[Item]:
    if not item_ids:
        return []
    result = await db.execute(
        select(Item).where(
            Item.id.in_(item_ids),
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    return list(result.scalars().all())


def _resolve_garment_urls(
    items: list[Item],
    top_item_id: UUID | None,
    bottom_item_id: UUID | None,
    outer_item_id: UUID | None,
) -> tuple[str | None, str | None]:
    """把用户选择的上衣/下衣/外套映射到阿里云 top/bottom URL。

    外套（outer）在没有明确选择上衣时，作为上装传入。
    """
    top_url: str | None = None
    bottom_url: str | None = None
    item_map = {item.id: item for item in items}

    if top_item_id and top_item_id in item_map:
        top_url = item_map[top_item_id].image_url
    if bottom_item_id and bottom_item_id in item_map:
        bottom_url = item_map[bottom_item_id].image_url
    if outer_item_id and outer_item_id in item_map and not top_url:
        top_url = item_map[outer_item_id].image_url

    return top_url, bottom_url


def _validate_public_url(url: str | None, name: str) -> None:
    if not url:
        return
    if url.startswith(("http://", "https://")):
        return
    raise BadRequestException(
        f"{name} 必须是公网可访问的 http/https URL，本地路径无法被阿里云识别"
    )


async def generate_tryon(
    db: AsyncSession,
    user_id: UUID,
    mode: str,
    person_image_url: str,
    top_item_id: UUID | None = None,
    bottom_item_id: UUID | None = None,
    outer_item_id: UUID | None = None,
) -> dict:
    """提交阿里云 OutfitAnyone 虚拟试衣任务。"""
    if not settings.tryon_api_key:
        raise AIException("虚拟试衣服务尚未配置 API Key")

    model = (
        settings.tryon_premium_model
        if mode == "premium"
        else settings.tryon_fast_model
    )

    # 校验输入图片 URL
    _validate_public_url(person_image_url, "人物照片")

    # 查询并校验衣物归属
    requested_ids = [i for i in [top_item_id, bottom_item_id, outer_item_id] if i]
    items = await _get_items(db, user_id, requested_ids)
    found_ids = {item.id for item in items}
    missing = set(requested_ids) - found_ids
    if missing:
        raise NotFoundException("部分衣物不存在或无权访问")

    top_url, bottom_url = _resolve_garment_urls(
        items, top_item_id, bottom_item_id, outer_item_id
    )
    if not top_url and not bottom_url:
        raise BadRequestException("请至少选择一件上装或下装")

    _validate_public_url(top_url, "上装图片")
    _validate_public_url(bottom_url, "下装图片")

    payload: dict = {
        "model": model,
        "input": {
            "person_image_url": person_image_url,
        },
        "parameters": {
            "resolution": -1,
            "restore_face": True,
        },
    }
    if top_url:
        payload["input"]["top_garment_url"] = top_url
    if bottom_url:
        payload["input"]["bottom_garment_url"] = bottom_url

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.tryon_base_url}/services/aigc/image2image/image-synthesis",
                headers={
                    "Authorization": f"Bearer {settings.tryon_api_key}",
                    "Content-Type": "application/json",
                    "X-DashScope-Async": "enable",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise AIException(f"虚拟试衣任务提交失败: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise AIException("虚拟试衣服务网络异常", timeout=True) from exc

    output = data.get("output", {})
    task_id = output.get("task_id")
    if not task_id:
        raise AIException("虚拟试衣服务未返回任务 ID")
    status = output.get("task_status", "PENDING").lower()

    tryon_result = TryonResult(
        user_id=user_id,
        mode=mode,
        model=model,
        person_image_url=person_image_url,
        top_garment_url=top_url,
        bottom_garment_url=bottom_url,
        outer_garment_url=None,
        task_id=task_id,
        status=status,
    )
    db.add(tryon_result)
    await db.commit()
    await db.refresh(tryon_result)

    return {
        "id": tryon_result.id,
        "task_id": tryon_result.task_id,
        "status": tryon_result.status,
    }


async def get_tryon_result(
    db: AsyncSession, user_id: UUID, result_id: UUID
) -> TryonResult:
    result = await db.execute(
        select(TryonResult).where(
            TryonResult.id == result_id, TryonResult.user_id == user_id
        )
    )
    tryon_result = result.scalar_one_or_none()
    if tryon_result is None:
        raise NotFoundException("试衣记录不存在")
    return tryon_result


def _extract_tryon_image_url(output: dict) -> str | None:
    """从阿里云不同版本响应结构中提取结果图 URL。"""
    # 1. VL/聊天式返回结构
    choices = output.get("choices", [])
    if choices and isinstance(choices, list):
        content = choices[0].get("message", {}).get("content", [])
        for c in content:
            if isinstance(c, dict) and c.get("type") == "image":
                return c.get("image")

    # 2. results 数组结构（如 text2image）
    results = output.get("results", [])
    if isinstance(results, list) and results:
        first = results[0]
        if isinstance(first, dict):
            return first.get("url") or first.get("image_url")

    # 3. results 对象结构（aitryon-plus 可能直接返回对象）
    if isinstance(results, dict):
        return results.get("image_url") or results.get("url")

    # 4. output 顶层字段兜底
    return output.get("image_url") or output.get("url")


async def refresh_tryon_result(
    db: AsyncSession, tryon_result: TryonResult
) -> TryonResult:
    """轮询阿里云任务状态并更新本地记录。"""
    if tryon_result.status in ("succeeded", "failed"):
        return tryon_result

    if not settings.tryon_api_key:
        raise AIException("虚拟试衣服务尚未配置 API Key")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{settings.tryon_base_url}/tasks/{tryon_result.task_id}",
                headers={"Authorization": f"Bearer {settings.tryon_api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise AIException(f"查询虚拟试衣任务失败: {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise AIException("虚拟试衣服务网络异常", timeout=True) from exc

    output = data.get("output", {})
    status = output.get("task_status", "UNKNOWN").lower()
    tryon_result.status = status

    if status == "succeeded":
        image_url = _extract_tryon_image_url(output)
        tryon_result.result_image_url = image_url
        if not image_url:
            tryon_result.status = "failed"
            tryon_result.error_message = f"服务未返回结果图片，原始响应: {data}"
    elif status == "failed":
        tryon_result.error_message = output.get("message", "生成失败")

    await db.commit()
    await db.refresh(tryon_result)
    return tryon_result


async def list_tryon_results(
    db: AsyncSession, user_id: UUID, limit: int = 20, offset: int = 0
) -> tuple[list[TryonResult], int]:
    stmt = (
        select(TryonResult)
        .where(TryonResult.user_id == user_id)
        .order_by(TryonResult.created_at.desc())
    )
    count_result = await db.execute(
        select(func.count()).select_from(stmt.subquery())
    )
    total = count_result.scalar() or 0

    result = await db.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all()), total
