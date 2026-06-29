from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.favorite import FavoriteItem, FavoritePost
from app.models.item import Item
from app.models.post import Post


async def list_favorites(db: AsyncSession, user_id: UUID) -> dict:
    post_result = await db.execute(
        select(FavoritePost, Post)
        .join(Post, FavoritePost.post_id == Post.id)
        .where(FavoritePost.user_id == user_id)
        .order_by(FavoritePost.created_at.desc())
    )
    posts = []
    for fav, post in post_result.all():
        posts.append(
            {
                "id": post.id,
                "author": post.author_name or "匿名用户",
                "avatar_color": post.author_avatar_color,
                "title": post.title,
                "cover_color": post.cover_color,
                "img_height": post.img_height,
                "like_count": post.like_count,
                "style": post.style,
                "favorited_at": fav.created_at,
                "image_url": post.images[0] if post.images else "",
            }
        )

    item_result = await db.execute(
        select(FavoriteItem, Item)
        .join(Item, FavoriteItem.item_id == Item.id)
        .where(
            FavoriteItem.user_id == user_id,
            Item.is_deleted.is_(False),
        )
        .order_by(FavoriteItem.created_at.desc())
    )
    items = []
    for fav, item in item_result.all():
        items.append(
            {
                "id": item.id,
                "name": item.name,
                "image_color": item.image_color,
                "price": item.price,
                "brand": item.brand,
                "favorited_at": fav.created_at,
                "image_url": item.image_url or "",
            }
        )

    return {"posts": posts, "items": items}


async def toggle_favorite_post(
    db: AsyncSession, user_id: UUID, post_id: UUID
) -> None:
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if post is None:
        raise NotFoundException("帖子不存在")

    fav_result = await db.execute(
        select(FavoritePost).where(
            FavoritePost.user_id == user_id,
            FavoritePost.post_id == post_id,
        )
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
    else:
        await db.execute(
            insert(FavoritePost)
            .values(user_id=user_id, post_id=post_id)
            .on_conflict_do_nothing(
                index_elements=["user_id", "post_id"]
            )
        )
    await db.commit()


async def toggle_favorite_item(
    db: AsyncSession, user_id: UUID, item_id: UUID
) -> None:
    item_result = await db.execute(
        select(Item).where(
            Item.id == item_id,
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
    )
    item = item_result.scalar_one_or_none()
    if item is None:
        raise NotFoundException("衣物不存在")

    fav_result = await db.execute(
        select(FavoriteItem).where(
            FavoriteItem.user_id == user_id,
            FavoriteItem.item_id == item_id,
        )
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
    else:
        await db.execute(
            insert(FavoriteItem)
            .values(user_id=user_id, item_id=item_id)
            .on_conflict_do_nothing(
                index_elements=["user_id", "item_id"]
            )
        )
    await db.commit()
