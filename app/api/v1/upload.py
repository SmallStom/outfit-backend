from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.core.exceptions import BadRequestException
from app.core.responses import success
from app.db.dependencies import CurrentUserId
from app.services.cos import get_cos_sts_credentials, upload_bytes_to_cos

router = APIRouter(prefix="/upload", tags=["upload"])

_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _is_valid_image_magic(content: bytes, suffix: str) -> bool:
    """通过文件头 Magic Bytes 校验图片格式。"""
    if len(content) < 8:
        return False
    if suffix in (".jpg", ".jpeg"):
        return content[:3] == b"\xff\xd8\xff"
    if suffix == ".png":
        return content[:8] == b"\x89PNG\r\n\x1a\n"
    if suffix == ".gif":
        return content[:6] in (b"GIF87a", b"GIF89a")
    if suffix == ".webp":
        # RIFF....WEBP
        return content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    return False


@router.post("/cos-sts")
async def cos_sts(user_id: CurrentUserId):
    credentials = await get_cos_sts_credentials(user_id)
    return success(data=credentials)


def _validate_image(file: UploadFile) -> tuple[str, bytes]:
    suffix = Path(file.filename or "image.jpg").suffix.lower()
    if suffix not in _ALLOWED_IMAGE_EXTENSIONS:
        raise BadRequestException("仅支持 jpg、jpeg、png、webp、gif 格式的图片")

    content = file.file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise BadRequestException("文件大小超过 10MB 限制")

    if not _is_valid_image_magic(content, suffix):
        raise BadRequestException("图片文件头与扩展名不符或已损坏")

    return suffix, content


@router.post("/local")
async def upload_local(
    file: UploadFile = File(...),
    user_id: CurrentUserId = None,
):
    """后端直传 COS，返回公网可访问 URL（不再保存到服务本地）。"""
    suffix, content = _validate_image(file)
    mime_ext = "jpeg" if suffix == ".jpg" else suffix.lstrip(".")
    url = await upload_bytes_to_cos(content, f"image/{mime_ext}", mime_ext)
    return success(data={"url": url})


@router.post("/tryon-person")
async def upload_tryon_person(
    file: UploadFile = File(...),
    user_id: CurrentUserId = None,
):
    """上传虚拟试衣用的人物照片，直传 COS 返回公网 URL。"""
    suffix, content = _validate_image(file)
    mime_ext = "jpeg" if suffix == ".jpg" else suffix.lstrip(".")
    url = await upload_bytes_to_cos(content, f"image/{mime_ext}", mime_ext)
    return success(data={"url": url})
