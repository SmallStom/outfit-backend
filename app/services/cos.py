import asyncio
from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj


def _cos_configured() -> bool:
    return bool(
        settings.cos_secret_id and settings.cos_secret_key and settings.cos_bucket
    )


def is_cos_configured() -> bool:
    """COS 是否已配置。"""
    return _cos_configured()


async def upload_bytes_to_cos(data: bytes, content_type: str, ext: str) -> str:
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
    key = f"items/{date_folder}/{uuid4().hex}.{ext}"
    await asyncio.to_thread(
        client.put_object,
        Bucket=settings.cos_bucket,
        Body=data,
        Key=key,
        ContentType=content_type,
        ACL="public-read",
    )
    return f"https://{settings.cos_bucket}.cos.{settings.cos_region}.myqcloud.com/{key}"


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
