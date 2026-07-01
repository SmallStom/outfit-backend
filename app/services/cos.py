import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj

logger = logging.getLogger(__name__)

_CONTENT_TYPE_MAP = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _cos_configured() -> bool:
    return bool(
        settings.cos_secret_id and settings.cos_secret_key and settings.cos_bucket
    )


def is_cos_configured() -> bool:
    """COS 是否已配置。"""
    return _cos_configured()


async def upload_bytes_to_cos(
    data: bytes, content_type: str, ext: str, folder: str = "items"
) -> str:
    """后端直传文件到 COS，返回公网可访问 URL。"""
    if not _cos_configured():
        raise BadRequestException("COS 未配置，无法上传文件")

    from qcloud_cos import CosConfig, CosS3Client

    config = CosConfig(
        Region=settings.cos_region,
        SecretId=settings.cos_secret_id,
        SecretKey=settings.cos_secret_key,
    )
    client = CosS3Client(config)

    date_folder = now_bj().strftime("%Y-%m-%d")
    key = f"{folder}/{date_folder}/{uuid4().hex}.{ext}"
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.cos_bucket,
        Body=data,
        Key=key,
        ContentType=content_type,
        ACL="public-read",
    )
    return f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com/{key}"


async def upload_image_url_to_cos(image_url: str, folder: str = "tryon") -> str:
    """下载远程图片并上传到 COS，返回 COS 公网 URL。

    下载失败或 COS 未配置时，返回原始 URL 作为兜底。
    """
    if not image_url or not _cos_configured():
        return image_url

    ext = "png"
    content_type = "image/png"
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(image_url)
            resp.raise_for_status()
            data = resp.content

            # 优先从响应头判断格式
            resp_content_type = resp.headers.get("content-type", "").lower()
            if resp_content_type in _CONTENT_TYPE_MAP:
                content_type = resp_content_type
                ext = _CONTENT_TYPE_MAP[resp_content_type]
            else:
                # 从 URL 路径推断扩展名
                suffix = Path(resp.url.path or image_url).suffix.lower().lstrip(".")
                if suffix in {"jpg", "jpeg", "png", "webp", "gif"}:
                    ext = "jpg" if suffix == "jpeg" else suffix
                    content_type = f"image/{ext}"

            return await upload_bytes_to_cos(data, content_type, ext, folder=folder)
    except Exception as exc:
        logger.warning("上传试衣结果图到 COS 失败，将使用原 URL: %s", exc)
        return image_url


async def get_cos_sts_credentials(user_id: str) -> dict:
    """生成腾讯云 COS 临时上传凭证；未配置密钥时抛出异常。"""
    if not _cos_configured():
        raise BadRequestException("COS 未配置，无法生成临时上传凭证")

    from qcloud_sts.sts import Sts

    config = {
        "secret_id": settings.cos_secret_id,
        "secret_key": settings.cos_secret_key,
        "bucket": settings.cos_bucket,
        "region": settings.cos_region,
        "duration_seconds": settings.cos_duration_seconds,
        "allow_prefix": settings.cos_allow_prefix.replace("*", f"{user_id}/{uuid4()}"),
        "allow_actions": [
            "name/cos:PutObject",
            "name/cos:PostObject",
        ],
    }
    sts = Sts(config)
    return await asyncio.to_thread(sts.get_credential)
