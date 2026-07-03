import asyncio
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj

logger = logging.getLogger(__name__)

_REMOTE_IMAGE_MAX_SIZE = 10 * 1024 * 1024
_REMOTE_IMAGE_TIMEOUT = 30.0
_MAX_REDIRECTS = 3


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


def _detect_image_format(content: bytes) -> str | None:
    if len(content) < 12:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    return None


def _is_forbidden_ip(address: str) -> bool:
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def _validate_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise BadRequestException("仅支持 http/https 图片链接")
    hostname = parsed.hostname
    if not hostname:
        raise BadRequestException("图片链接格式不正确")
    if hostname.lower() == "localhost":
        raise BadRequestException("该图片链接不受支持")
    try:
        if _is_forbidden_ip(hostname):
            raise BadRequestException("该图片链接不受支持")
    except ValueError:
        pass

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
    except socket.gaierror:
        raise BadRequestException("图片链接域名无法解析")
    for info in infos:
        if _is_forbidden_ip(info[4][0]):
            raise BadRequestException("该图片链接不受支持")


async def _download_remote_image(image_url: str) -> tuple[bytes, str, str]:
    current_url = image_url
    async with httpx.AsyncClient(timeout=_REMOTE_IMAGE_TIMEOUT, follow_redirects=False) as client:
        for redirect_count in range(_MAX_REDIRECTS + 1):
            await _validate_public_http_url(current_url)
            async with client.stream("GET", current_url) as resp:
                if resp.status_code in {301, 302, 303, 307, 308}:
                    location = resp.headers.get("location")
                    if not location:
                        raise BadRequestException("图片跳转地址无效")
                    if redirect_count >= _MAX_REDIRECTS:
                        raise BadRequestException("图片跳转次数过多")
                    current_url = str(resp.url.join(location))
                    continue

                resp.raise_for_status()
                content_type_header = resp.headers.get("content-type", "").split(";", 1)[0].lower()
                if content_type_header and not content_type_header.startswith("image/"):
                    raise BadRequestException("链接内容不是图片")

                chunks: list[bytes] = []
                total = 0
                async for chunk in resp.aiter_bytes():
                    total += len(chunk)
                    if total > _REMOTE_IMAGE_MAX_SIZE:
                        raise BadRequestException("图片大小超过 10MB 限制")
                    chunks.append(chunk)

                data = b"".join(chunks)
                ext = _detect_image_format(data)
                if ext is None:
                    raise BadRequestException("无法识别的图片格式或文件已损坏")
                content_type = "image/jpeg" if ext == "jpg" else f"image/{ext}"
                return data, content_type, ext

    raise BadRequestException("图片下载失败")


async def upload_image_url_to_cos(
    image_url: str,
    folder: str = "tryon",
    fallback_to_original: bool = True,
) -> str:
    """下载远程图片并上传到 COS，返回 COS 公网 URL。"""
    if not image_url:
        return image_url
    if not _cos_configured():
        if fallback_to_original:
            return image_url
        raise BadRequestException("COS 未配置，无法上传文件")

    try:
        data, content_type, ext = await _download_remote_image(image_url)
        return await upload_bytes_to_cos(data, content_type, ext, folder=folder)
    except BadRequestException:
        if fallback_to_original:
            logger.warning("上传远程图片到 COS 失败，将使用原 URL")
            return image_url
        raise
    except Exception as exc:
        logger.warning("上传远程图片到 COS 失败，将使用原 URL: %s", exc)
        if fallback_to_original:
            return image_url
        raise BadRequestException("图片下载失败，请重试或换一张")


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
