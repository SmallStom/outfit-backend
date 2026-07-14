"""衣物提取服务：通过 OpenAI 兼容 images/edits 接口提取衣物（纯白背景），
从响应中提取图片数据并用 Pillow 验证是否成功提取到衣物。"""
from __future__ import annotations

import asyncio
import base64
import io
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AIException

logger = logging.getLogger(__name__)

GARMENT_EXTRACTION_PROMPT = (
    "Extract the main clothing garment from this image. "
    "Remove the entire background completely, including any person, mannequin, "
    "hanger, props, or surface. Output only the garment itself centered on a "
    "pure white background (#FFFFFF), showing the front view of the garment. "
    "Preserve every detail: its exact silhouette, color, pattern, texture, "
    "stitching, folds, buttons, zippers, and natural shading. Do not alter, "
    "resize, restyle, or recolor the garment. The result must be a clean "
    "cutout of only the clothing item on a solid white background."
)

_GARMENT_NOT_FOUND_MSG = "未检测到衣物，请重新拍照上传标准衣物图片"

# 白色像素判定阈值：RGB 均高于此值视为白色背景
_WHITE_THRESHOLD = 240


async def _download_image_direct(url: str) -> tuple[bytes, str]:
    """从可信 URL 直接下载图片（跳过 SSRF 检查，trust_env=False 绕过代理）。"""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, trust_env=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, content_type


async def _call_image_edit_api(image_url: str) -> dict:
    """调用 OpenAI 兼容 images/edits 接口，返回原始 JSON 响应。

    流程：下载原图 -> multipart form-data 上传 -> 返回 JSON。
    502/503/504 时自动重试（最多 3 次）。
    """
    if not settings.image_edit_api_key:
        raise AIException("衣物提取 API 尚未配置 API Key")

    # 1. 下载原图
    image_data, content_type = await _download_image_direct(image_url)
    ext = "jpg" if "jpeg" in content_type or "jpg" in content_type else "png"

    # 2. 构建 multipart form data
    files = {"image": (f"input.{ext}", image_data, content_type)}
    data = {
        "model": settings.image_edit_model,
        "prompt": GARMENT_EXTRACTION_PROMPT,
        "n": "1",
        "size": settings.image_edit_size,
        "quality": settings.image_edit_quality,
        "background": "opaque",
        "output_format": "png",
    }

    url = f"{settings.image_edit_base_url}/images/edits"

    # 3. 调用 API（带重试）
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {settings.image_edit_api_key}"},
                    files=files,
                    data=data,
                )
                # 502/503/504 时重试
                if resp.status_code in (502, 503, 504) and attempt < 2:
                    logger.warning(
                        "images/edits 返回 %d，第 %d 次重试...",
                        resp.status_code, attempt + 1,
                    )
                    await asyncio.sleep(3)
                    continue
                resp.raise_for_status()
                return resp.json()
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < 2:
                logger.warning("images/edits 网络异常，第 %d 次重试: %s", attempt + 1, exc)
                await asyncio.sleep(3)
                continue
            raise AIException("衣物提取 API 网络异常", timeout=True) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "images/edits 衣物提取失败: %s - %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise AIException("衣物提取失败，请稍后重试") from exc

    raise AIException("衣物提取 API 多次重试后仍失败，请稍后重试") from last_exc


async def _extract_image_from_response(data: dict) -> tuple[bytes, str]:
    """从 OpenAI images/edits 响应中提取图片字节。

    支持的格式：
    1. {"data": [{"b64_json": "..."}]}  (OpenAI gpt-image-1 标准格式)
    2. {"data": [{"url": "https://..."}]}
    3. {"images": [{"b64_json": "..."}]}
    4. {"images": [{"url": "https://..."}]}
    5. {"images": ["data:image/png;base64,..."]}
    6. {"images": ["https://..."]}
    """
    items = data.get("data") or data.get("images") or []
    if not items:
        raise AIException("衣物提取 API 未返回结果图片")

    first = items[0]

    # dict 格式：b64_json 或 url
    if isinstance(first, dict):
        b64 = first.get("b64_json") or first.get("b64")
        if b64 and isinstance(b64, str):
            logger.info("API 返回 b64_json 格式图片")
            return base64.b64decode(b64), "image/png"
        url = first.get("url")
        if url and isinstance(url, str):
            logger.info("API 返回 URL 格式，下载: %s", url[:100])
            return await _download_image_direct(url)

    # string 格式
    if isinstance(first, str):
        if first.startswith("data:"):
            logger.info("API 返回 data URL 格式图片")
            _, b64 = first.split(",", 1)
            return base64.b64decode(b64), "image/png"
        if first.startswith("http"):
            logger.info("API 返回 URL 格式，下载: %s", first[:100])
            return await _download_image_direct(first)
        # raw base64
        try:
            decoded = base64.b64decode(first, validate=True)
            if len(decoded) > 100:
                logger.info("API 返回 raw base64 格式图片")
                return decoded, "image/png"
        except Exception:
            pass

    raise AIException("衣物提取 API 返回的图片格式无法识别")


def validate_garment_image(image_data: bytes) -> bool:
    """验证提取结果是否包含有效衣物（非纯白空图）。

    统计非白色像素占比：
    - 占比 < 3% -> False（几乎全白，提取失败）
    - 否则 -> True
    """
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
    except Exception:
        logger.warning("无法打开提取结果图片进行验证")
        return False

    # 缩小采样以加速：缩放到 100x100
    img = img.resize((100, 100))
    pixels = list(img.getdata())
    total = len(pixels)
    if total == 0:
        return False

    non_white = sum(
        1 for r, g, b in pixels
        if not (r >= _WHITE_THRESHOLD and g >= _WHITE_THRESHOLD and b >= _WHITE_THRESHOLD)
    )
    ratio = non_white / total
    if ratio < 0.03:
        logger.warning("提取结果非白色像素占比 %.1f%%，判定为提取失败", ratio * 100)
        return False

    return True


async def extract_and_validate_garment(image_url: str) -> tuple[bytes, str]:
    """完整提取流程：调用 images/edits -> 提取图片 -> 验证 -> 返回 (image_data, content_type)。

    如果验证失败，raise AIException。
    """
    # 1. 调用 images/edits API
    data = await _call_image_edit_api(image_url)

    # 2. 从响应中提取图片字节
    image_data, content_type = await _extract_image_from_response(data)

    logger.info(
        "衣物提取成功，图片大小=%.1fKB, content_type=%s",
        len(image_data) / 1024,
        content_type,
    )

    # 3. 验证是否成功提取到衣物（非纯白空图）
    if not validate_garment_image(image_data):
        raise AIException(_GARMENT_NOT_FOUND_MSG)

    return image_data, content_type
