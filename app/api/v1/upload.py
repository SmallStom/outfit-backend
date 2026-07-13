from fastapi import APIRouter, File, UploadFile

from app.core.responses import success
from app.db.dependencies import CurrentUserId
from app.schemas.upload import (
    EcommerceImagesResponse,
    EcommerceUrlRequest,
    RemoteImageRequest,
    RemoteImageResponse,
)
from app.services.cos import get_cos_sts_credentials, upload_bytes_to_cos, upload_image_url_to_cos
from app.services.ecommerce_image_service import fetch_ecommerce_images
from app.services.image_util import validate_image

router = APIRouter(prefix="/upload", tags=["upload"])


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
    suffix, content = validate_image(file)
    mime_ext = "jpeg" if suffix == ".jpg" else suffix.lstrip(".")
    url = await upload_bytes_to_cos(content, f"image/{mime_ext}", mime_ext)
    return success(data={"url": url})


@router.post("/tryon-person")
async def upload_tryon_person(
    file: UploadFile = File(...),
    user_id: CurrentUserId = None,
):
    """上传虚拟试衣用的人物照片，直传 COS 返回公网 URL。"""
    suffix, content = validate_image(file)
    mime_ext = "jpeg" if suffix == ".jpg" else suffix.lstrip(".")
    url = await upload_bytes_to_cos(content, f"image/{mime_ext}", mime_ext)
    return success(data={"url": url})


@router.post("/fetch-ecommerce-images")
async def upload_fetch_ecommerce_images(
    body: EcommerceUrlRequest,
    user_id: CurrentUserId = None,
):
    """根据电商商品链接抓取主图/详情图候选列表。"""
    result = await fetch_ecommerce_images(body.url)
    return success(data=EcommerceImagesResponse.model_validate(result).model_dump(by_alias=True))


@router.post("/download-remote-image")
async def upload_download_remote_image(
    body: RemoteImageRequest,
    user_id: CurrentUserId = None,
):
    """将用户选中的远程图片下载并转存 COS，返回 COS 公网 URL。"""
    cos_url = await upload_image_url_to_cos(
        body.url,
        folder="items",
        fallback_to_original=False,
    )
    return success(data=RemoteImageResponse(url=cos_url).model_dump(by_alias=True))
