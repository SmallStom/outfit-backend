import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, UploadFile

from app.core.responses import success
from app.db.dependencies import CurrentUserId
from app.services.cos import get_cos_sts_credentials

router = APIRouter(prefix="/upload", tags=["upload"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


@router.post("/cos-sts")
async def cos_sts(user_id: CurrentUserId):
    credentials = get_cos_sts_credentials(user_id)
    return success(data=credentials)


@router.post("/local")
async def upload_local(file: UploadFile = File(...)):
    """开发测试用本地上传，保存到 /uploads 目录并通过 /uploads/<filename> 访问。"""
    suffix = Path(file.filename or "image.jpg").suffix
    filename = f"{uuid4().hex}{suffix}"
    dest = UPLOAD_DIR / filename
    with dest.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return success(data={"url": f"/uploads/{filename}"})
