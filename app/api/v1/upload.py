from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile

from app.core.exceptions import BadRequestException
from app.core.responses import success
from app.db.dependencies import CurrentUserId
from app.services.cos import get_cos_sts_credentials

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

_MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


@router.post("/cos-sts")
async def cos_sts(user_id: CurrentUserId):
    credentials = await get_cos_sts_credentials(user_id)
    return success(data=credentials)


@router.post("/local")
async def upload_local(
    file: UploadFile = File(...),
    user_id: CurrentUserId = None,
):
    """本地上传（已限制图片格式与大小）。"""
    suffix = Path(file.filename or "image.jpg").suffix.lower()
    if suffix not in _ALLOWED_IMAGE_EXTENSIONS:
        raise BadRequestException("仅支持 jpg、jpeg、png、webp、gif 格式的图片")

    content = await file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise BadRequestException("文件大小超过 10MB 限制")

    filename = f"{uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / filename
    dest.write_bytes(content)
    return success(data={"url": f"/uploads/{filename}"})
