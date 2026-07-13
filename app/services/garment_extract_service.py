"""衣物提取服务：通过 HighwayAPI GPT Image 2 Edit 提取衣物（纯白背景），
下载结果并用 Pillow 验证是否成功提取到衣物。"""
from __future__ import annotations

import io
import logging

import httpx

from app.core.config import settings
from app.core.exceptions import AIException
from app.services.cos import _download_remote_image

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


async def extract_garment(image_url: str) -> str:
    """调用 HighwayAPI GPT Image 2 Edit 提取衣物，返回结果图 URL。

    失败直接 raise AIException，不回退阿里云。
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
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.error(
            "HighwayAPI 衣物提取失败: %s - %s",
            exc.response.status_code,
            exc.response.text,
        )
        raise AIException("衣物提取失败，请稍后重试") from exc
    except httpx.RequestError as exc:
        raise AIException("HighwayAPI 网络异常", timeout=True) from exc

    images = data.get("images") or []
    image_url_result = images[0] if images else None
    if not image_url_result:
        raise AIException("HighwayAPI 未返回结果图片")

    return image_url_result


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
    """完整提取流程：调用 HighwayAPI -> 下载结果 -> 验证 -> 返回 (image_data, content_type)。

    如果验证失败，raise AIException。
    """
    # 1. 调用 HighwayAPI 提取衣物（白色背景）
    highway_url = await extract_garment(image_url)

    # 2. 下载结果图片（复用 cos.py 的下载逻辑，含 SSRF 防护）
    data, content_type, _ext = await _download_remote_image(highway_url)

    # 3. 验证是否成功提取到衣物（非纯白空图）
    if not validate_garment_image(data):
        raise AIException(_GARMENT_NOT_FOUND_MSG)

    return data, content_type
