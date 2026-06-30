import base64
import re
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.core.timezone import now_bj
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate
from app.schemas.wear_history import WearHistoryCreate
from app.services.cos import is_cos_configured, upload_bytes_to_cos
from app.services.wear_history_service import create_history


_BASE64_IMAGE_RE = re.compile(r"^data:image/(\w+);base64,(.*)$")


async def _save_base64_image(image_base64: str, base_url: str) -> str:
    """将 base64 图片直传到 COS，返回公网 URL。"""
    match = _BASE64_IMAGE_RE.match(image_base64)
    if not match:
        return image_base64

    mime_ext, b64data = match.groups()
    ext = "jpg" if mime_ext == "jpeg" else mime_ext
    try:
        data = base64.b64decode(b64data)
    except Exception:
        raise BadRequestException("图片 base64 解码失败")

    if not is_cos_configured():
        raise BadRequestException("图片存储 COS 未配置，无法保存图片")

    return await upload_bytes_to_cos(data, f"image/{mime_ext}", ext)


async def create_item(
    db: AsyncSession, user_id: UUID, data: ItemCreate, base_url: str
) -> Item:
    item_data = data.model_dump()

    # 处理前端通过 image 字段传入的 base64 图片
    image_base64 = item_data.pop("image", None)
    image_url = item_data.get("image_url")
    if image_base64 and image_base64.startswith("data:"):
        image_url = await _save_base64_image(image_base64, base_url)
    elif image_url and image_url.startswith("data:"):
        image_url = await _save_base64_image(image_url, base_url)

    item_data["image_url"] = image_url or ""
    item = Item(user_id=user_id, wear_count=0, **item_data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


async def list_items(
    db: AsyncSession,
    user_id: UUID,
    category: str | None = None,
    tag: str | None = None,
    search: str | None = None,
) -> list[Item]:
    stmt = (
        select(Item)
        .where(Item.user_id == user_id, Item.is_deleted.is_(False))
        .order_by(Item.created_at.desc())
    )
    if category and category != "all":
        stmt = stmt.where(Item.category == category)
    if tag:
        stmt = stmt.where(Item.tags.contains([tag]))
    if search:
        q = f"%{search}%"
        stmt = stmt.where(
            or_(
                Item.name.ilike(q),
                Item.brand.ilike(q),
                Item.tags.any(search),
            )
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_item(db: AsyncSession, user_id: UUID, item_id: UUID) -> Item:
    result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("衣物不存在")
    return item


async def update_item(
    db: AsyncSession,
    user_id: UUID,
    item_id: UUID,
    data: ItemUpdate,
    base_url: str,
) -> Item:
    item = await get_item(db, user_id, item_id)
    update_data = data.model_dump(exclude={"item_ids"}, exclude_unset=True)
    image_url = update_data.get("image_url")
    if image_url and image_url.startswith("data:"):
        update_data["image_url"] = await _save_base64_image(image_url, base_url)
    for key, value in update_data.items():
        setattr(item, key, value)
    await db.commit()
    await db.refresh(item)
    return item


async def delete_item(db: AsyncSession, user_id: UUID, item_id: UUID) -> None:
    item = await get_item(db, user_id, item_id)
    item.is_deleted = True
    await db.commit()


async def record_wear(db: AsyncSession, user_id: UUID, item_id: UUID) -> Item:
    # 先校验衣物存在且属于当前用户
    item = await get_item(db, user_id, item_id)

    # 复用 create_history：它会校验归属、写入历史并原子更新穿着统计
    await create_history(
        db=db,
        user_id=user_id,
        data=WearHistoryCreate(
            date=now_bj().date(),
            weather="",
            occasion="",
            item_ids=[item_id],
            note="记录穿着",
        ),
    )

    # 重新读取以获取更新后的 wear_count / last_worn_at
    refreshed = await db.execute(select(Item).where(Item.id == item_id))
    return refreshed.scalar_one()


COMMON_TAGS = [
    "T恤", "衬衫", "毛衣", "开衫", "卫衣", "吊带", "Polo",
    "牛仔裤", "西裤", "半裙", "工装裤", "阔腿裤", "短裤",
    "风衣", "西装", "皮衣", "羽绒服", "外套",
    "运动鞋", "靴子", "小白鞋", "乐福鞋", "高跟鞋",
    "腰带", "围巾", "包包", "耳饰",
    "通勤", "休闲", "复古", "街头", "基础款", "修身", "宽松", "温柔", "优雅", "酷飒", "慵懒",
    "白色", "黑色", "蓝色", "绿色", "灰色", "米色", "驼色", "卡其",
    "纯棉", "羊绒", "真丝", "亚麻", "羊毛", "真皮",
]
