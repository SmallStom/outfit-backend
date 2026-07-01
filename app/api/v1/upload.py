from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from app.core.exceptions import BadRequestException
from app.core.responses import success
from app.db.dependencies import CurrentUserId
from app.services.cos import get_cos_sts_credentials, upload_bytes_to_cos

router = APIRouter(prefix="/upload", tags=["upload"])

_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


def _detect_image_format(content: bytes) -> str | None:
    """通过文件头 Magic Bytes 推断真实图片格式，返回标准化扩展名（不含点）。"""
    if len(content) < 8:
        return None
    if content[:3] == b"\xff\xd8\xff":
        return "jpg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    # HEIC/HEIF 文件头（ftyp 盒子）
    if content[4:8] == b"ftyp" and content[8:12] in (b"heic", b"heix", b"hevc", b"mif1"):
        return "heic"
    return None


def _validate_image(file: UploadFile) -> tuple[str, bytes]:
    """校验图片并返回真实扩展名与内容。

    优先根据文件头推断真实格式，避免前端/系统临时文件名扩展名不准确导致误报。
    """
    content = file.file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise BadRequestException("文件大小超过 10MB 限制")

    real_ext = _detect_image_format(content)
    if real_ext is None:
        raise BadRequestException("无法识别的图片格式或文件已损坏")

    if real_ext == "heic":
        raise BadRequestException("不支持 HEIC 格式，请上传 jpg、png、webp 或 gif 格式图片")

    suffix = Path(file.filename or "image.jpg").suffix.lower()
    if suffix and suffix not in _ALLOWED_IMAGE_EXTENSIONS:
        # 文件名扩展名不在白名单，但文件头识别为支持的格式时，以文件头为准
        if real_ext not in {"jpg", "jpeg", "png", "webp", "gif"}:
            raise BadRequestException("仅支持 jpg、jpeg、png、webp、gif 格式的图片")

    return f".{real_ext}", content


@router.post("/cos-sts")
async def cos_sts(user_id: CurrentUserId):
    credentials = await get_cos_sts_credentials(user_id)
    return success(data=credentials)


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
