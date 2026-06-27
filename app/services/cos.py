from uuid import uuid4

from app.core.config import settings
from app.core.exceptions import BadRequestException


def get_cos_sts_credentials(user_id: str) -> dict:
    """生成腾讯云 COS 临时上传凭证；未配置密钥时抛出异常。"""
    if not settings.cos_secret_id or not settings.cos_secret_key or not settings.cos_bucket:
        raise BadRequestException("COS 未配置，请使用 /upload/local 本地上传接口")

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
    return sts.get_credential()
