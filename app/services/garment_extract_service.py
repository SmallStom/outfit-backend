"""衣物提取服务：通过 HighwayAPI GPT Image 2 Edit 提取衣物（纯白背景），
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


async def _call_highway_api(image_url: str) -> dict:
    """调用 HighwayAPI GPT Image 2 Edit，返回原始 JSON 响应。

    504 网关超时时自动重试（最多 3 次）。
    """
    if not settings.highway_api_key:
        raise AIException("HighwayAPI 尚未配置 API Key")

    payload: dict = {
        "n": 1,
        "image": [image_url],
        "prompt": GARMENT_EXTRACTION_PROMPT,
        "size": settings.highway_tryon_size,
        "quality": settings.highway_extract_quality,
        "background": "opaque",
        "output_format": "png",
    }

    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{settings.highway_base_url}/{settings.highway_tryon_model}",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {settings.highway_api_key}",
                    },
                    json=payload,
                )
                # 504/502/503 时重试
                if resp.status_code in (502, 503, 504) and attempt < 2:
                    logger.warning(
                        "HighwayAPI 返回 %d，第 %d 次重试...",
                        resp.status_code, attempt + 1,
                    )
                    await asyncio.sleep(3)
                    continue
                resp.raise_for_status()
                return resp.json()
        except httpx.RequestError as exc:
            last_exc = exc
            if attempt < 2:
                logger.warning("HighwayAPI 网络异常，第 %d 次重试: %s", attempt + 1, exc)
                await asyncio.sleep(3)
                continue
            raise AIException("HighwayAPI 网络异常", timeout=True) from exc
        except httpx.HTTPStatusError as exc:
            logger.error(
                "HighwayAPI 衣物提取失败: %s - %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            raise AIException("衣物提取失败，请稍后重试") from exc

    raise AIException("HighwayAPI 多次重试后仍失败，请稍后重试") from last_exc


async def _download_image_direct(url: str) -> tuple[bytes, str]:
    """从可信 URL 直接下载图片（HighwayAPI 返回的 CDN 链接，跳过 SSRF 检查）。"""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, trust_env=False) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/png").split(";")[0].strip()
        return resp.content, content_type


async def _extract_image_from_response(data: dict) -> tuple[bytes, str]:
    """从 HighwayAPI 响应中提取图片字节，兼容多种返回格式。

    支持的格式：
    1. {"images": [{"b64_json": "..."}]}
    2. {"images": [{"url": "https://..."}]}
    3. {"images": ["data:image/png;base64,..."]}
    4. {"images": ["https://..."]}
    5. {"data": [{"b64_json": "..."}]}  (OpenAI 原始格式)
    """
    images = data.get("images") or data.get("data") or []
    if not images:
        raise AIException("HighwayAPI 未返回结果图片")

    first = images[0]

    # 格式 1/5: dict with b64_json or url
    if isinstance(first, dict):
        b64 = first.get("b64_json") or first.get("b64")
        if b64 and isinstance(b64, str):
            logger.info("HighwayAPI 返回 b64_json 格式图片")
            return base64.b64decode(b64), "image/png"
        url = first.get("url")
        if url and isinstance(url, str):
            logger.info("HighwayAPI 返回 dict.url 格式，下载: %s", url[:100])
            return await _download_image_direct(url)

    # 格式 2/4: string
    if isinstance(first, str):
        if first.startswith("data:"):
            # data:image/png;base64,iVBOR...
            logger.info("HighwayAPI 返回 data URL 格式图片")
            _, b64 = first.split(",", 1)
            return base64.b64decode(b64), "image/png"
        if first.startswith("http"):
            logger.info("HighwayAPI 返回 URL 格式，下载: %s", first[:100])
            return await _download_image_direct(first)
        # 尝试当 raw base64 解码
        try:
            decoded = base64.b64decode(first, validate=True)
            if len(decoded) > 100:
                logger.info("HighwayAPI 返回 raw base64 格式图片")
                return decoded, "image/png"
        except Exception:
            pass

    raise AIException("HighwayAPI 返回的图片格式无法识别")


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
    """完整提取流程：调用 HighwayAPI -> 提取图片 -> 验证 -> 返回 (image_data, content_type)。

    如果验证失败，raise AIException。
    """
    # 1. 调用 HighwayAPI
    data = await _call_highway_api(image_url)

    # 2. 从响应中提取图片字节（兼容 base64 / data URL / URL 等格式）
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
