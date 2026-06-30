import io
import logging
from uuid import UUID, uuid4

import httpx
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AIException, BadRequestException, ForbiddenException, NotFoundException
from app.models.item import Item
from app.models.model_template import ModelTemplate
from app.models.puzzle_result import PuzzleResult
from app.services.cos import upload_bytes_to_cos
from app.services.quota_service import deduct_for_puzzle
from app.services.task_service import complete_task

logger = logging.getLogger(__name__)


async def list_templates(db: AsyncSession) -> list[ModelTemplate]:
    result = await db.execute(
        select(ModelTemplate)
        .where(ModelTemplate.is_active.is_(True))
        .order_by(ModelTemplate.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: UUID) -> ModelTemplate:
    result = await db.execute(
        select(ModelTemplate).where(
            ModelTemplate.id == template_id,
            ModelTemplate.is_active.is_(True),
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        raise NotFoundException("模特模板不存在或已下架")
    return template


async def generate_puzzle(
    db: AsyncSession,
    user_id: UUID,
    template_id: UUID,
    item_ids: list[UUID],
) -> dict:
    """生成拼图：抠图 → 拼接 → 上传 COS → 持久化结果。"""
    if not settings.tryon_segment_api_key:
        raise AIException("拼图抠图服务尚未配置 API Key")

    # 额度校验与扣减
    quota = await deduct_for_puzzle(db=db, user_id=user_id)
    if not quota.get("allowed") or not quota.get("deducted"):
        raise ForbiddenException("拼图次数已用完，请开通会员或购买积分")

    template = await get_template(db, template_id)

    # 查询并校验衣物归属
    result = await db.execute(
        select(Item).where(
            Item.id.in_(item_ids),
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    items = list(result.scalars().all())
    if len(items) != len(item_ids):
        raise BadRequestException("部分衣物不存在或无权访问")

    # 校验每件衣物对应模板中存在的 slot
    slots = template.slots or {}
    for item in items:
        if item.category not in slots:
            raise BadRequestException(f"模板不支持衣物分类: {item.category}")

    puzzle_result = PuzzleResult(
        user_id=user_id,
        template_id=template_id,
        item_ids=item_ids,
        status="pending",
        task_id=str(uuid4()),
    )
    db.add(puzzle_result)
    await db.commit()
    await db.refresh(puzzle_result)

    try:
        # 1. 抠图
        cutout_urls: dict[str, str] = {}
        for item in items:
            cutout_url = await _cutout_garment(item.image_url, item.category)
            cutout_urls[item.category] = cutout_url

        puzzle_result.cutout_image_urls = cutout_urls
        await db.commit()

        # 2. 拼接
        result_bytes = await _composite_puzzle(template.template_image_url, cutout_urls, slots)

        # 3. 上传结果
        result_url = await upload_bytes_to_cos(result_bytes, "image/png", "png")

        puzzle_result.result_image_url = result_url
        puzzle_result.status = "succeeded"
        await db.commit()
        await db.refresh(puzzle_result)

        # 触发首次拼图任务
        await complete_task(db=db, user_id=user_id, trigger_event="first_puzzle")

    except Exception as exc:
        logger.exception("拼图生成失败")
        puzzle_result.status = "failed"
        puzzle_result.error_message = str(exc)
        await db.commit()
        raise AIException("拼图生成失败，请稍后重试") from exc

    return {
        "id": puzzle_result.id,
        "task_id": puzzle_result.task_id,
        "status": puzzle_result.status,
        "result_image_url": puzzle_result.result_image_url,
    }


async def get_puzzle_result(
    db: AsyncSession, user_id: UUID, result_id: UUID
) -> PuzzleResult:
    result = await db.execute(
        select(PuzzleResult).where(
            PuzzleResult.id == result_id,
            PuzzleResult.user_id == user_id,
        )
    )
    puzzle_result = result.scalar_one_or_none()
    if puzzle_result is None:
        raise NotFoundException("拼图记录不存在")
    return puzzle_result


async def list_puzzle_results(
    db: AsyncSession, user_id: UUID, limit: int = 20, offset: int = 0
) -> tuple[list[PuzzleResult], int]:
    stmt = (
        select(PuzzleResult)
        .where(PuzzleResult.user_id == user_id)
        .order_by(PuzzleResult.created_at.desc())
    )
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all()), total


_CATEGORY_TO_CLOTHES_TYPE = {
    "top": "upper",
    "bottom": "lower",
    "dress": "dress",
    "outer": "upper",
}


async def _cutout_garment(image_url: str, category: str) -> str:
    """调用阿里云 AI 试衣-图片分割接口，返回带透明通道的服饰图 URL。

    官方文档：https://help.aliyun.com/zh/model-studio/aitryon-parsing-api
    注意：该接口要求输入图为含完整人物的模特图，从模特身上分割出指定服饰区域。
    """
    clothes_type = _CATEGORY_TO_CLOTHES_TYPE.get(category)
    if clothes_type is None:
        raise BadRequestException(f"不支持的拼图衣物分类: {category}")

    payload = {
        "model": settings.tryon_segment_model,
        "input": {
            "image_url": image_url,
        },
        "parameters": {
            "clothes_type": [clothes_type],
        },
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{settings.tryon_segment_base_url}/services/vision/image-process/process",
                headers={
                    "Authorization": f"Bearer {settings.tryon_segment_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error("抠图请求失败: %s - %s", exc.response.status_code, exc.response.text)
        raise AIException("抠图服务调用失败") from exc
    except httpx.RequestError as exc:
        raise AIException("抠图服务网络异常", timeout=True) from exc

    output = data.get("output", {})
    parsing_urls = output.get("parsing_img_url") or []
    crop_urls = output.get("crop_img_url") or []

    # parsing_img_url 为 RGBA 透明底服饰图，优先用于拼图
    image_url = parsing_urls[0] if parsing_urls else (crop_urls[0] if crop_urls else None)
    if not image_url:
        logger.error("抠图服务未返回图片 URL: %s", data)
        raise AIException("抠图服务未返回图片")
    return image_url


async def _download_image(url: str) -> Image.Image:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGBA")


def _composite_puzzle_sync(
    template_image: Image.Image,
    cutout_images: dict[str, Image.Image],
    slots: dict,
) -> bytes:
    """同步拼接：按 z 层级将衣物贴到模板上。

    slots 支持相对坐标（推荐，0.0~1.0）或绝对像素（兼容旧数据）。
    """
    canvas = template_image.copy().convert("RGBA")
    template_w, template_h = canvas.size

    # 按 z 排序
    ordered = sorted(
        [(cat, slot) for cat, slot in slots.items() if cat in cutout_images],
        key=lambda x: x[1].get("z", 0),
    )

    for category, slot in ordered:
        garment = cutout_images[category]

        # 解析坐标：小于 1 视为相对比例，否则视为绝对像素
        raw_x = slot.get("x", 0)
        raw_y = slot.get("y", 0)
        x = int(raw_x * template_w) if isinstance(raw_x, (int, float)) and raw_x < 1 else int(raw_x)
        y = int(raw_y * template_h) if isinstance(raw_y, (int, float)) and raw_y < 1 else int(raw_y)

        # 缩放：优先使用相对 scale，其次使用绝对 width/height
        scale = slot.get("scale")
        if scale is not None:
            width = int(scale * template_w)
            ratio = width / max(garment.width, 1)
            height = int(garment.height * ratio)
        else:
            width = int(slot.get("width", garment.width))
            height = int(slot.get("height", garment.height))

        garment = garment.resize((width, height), Image.Resampling.LANCZOS)

        # 若衣物有 alpha 通道则作为 mask
        if garment.mode == "RGBA":
            canvas.paste(garment, (x, y), garment)
        else:
            canvas.paste(garment, (x, y))

    # 转为 PNG bytes
    output = io.BytesIO()
    canvas.convert("RGB").save(output, format="PNG")
    return output.getvalue()


async def _composite_puzzle(
    template_image_url: str,
    cutout_urls: dict[str, str],
    slots: dict,
) -> bytes:
    """异步下载图片并调用同步拼接函数。"""
    template_image = await _download_image(template_image_url)
    cutout_images = {}
    for category, url in cutout_urls.items():
        cutout_images[category] = await _download_image(url)

    import asyncio
    return await asyncio.to_thread(_composite_puzzle_sync, template_image, cutout_images, slots)
