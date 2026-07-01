from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.favorite import FavoriteItem, FavoritePost, FavoriteTryonResult
from app.models.item import Item
from app.models.post import Post
from app.models.tryon_result import TryonResult


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

    tryon_result = await db.execute(
        select(FavoriteTryonResult, TryonResult)
        .join(TryonResult, FavoriteTryonResult.tryon_result_id == TryonResult.id)
        .where(
            FavoriteTryonResult.user_id == user_id,
        )
        .order_by(FavoriteTryonResult.created_at.desc())
    )
    tryon_results = []
    for fav, result in tryon_result.all():
        tryon_results.append(
            {
                "id": result.id,
                "result_image_url": result.result_image_url or "",
                "person_image_url": result.person_image_url,
                "top_garment_url": result.top_garment_url,
                "bottom_garment_url": result.bottom_garment_url,
                "outer_garment_url": result.outer_garment_url,
                "mode": result.mode,
                "favorited_at": fav.created_at,
            }
        )

    return {"posts": posts, "items": items, "tryon_results": tryon_results}


async def is_tryon_result_favorited(
    db: AsyncSession, user_id: UUID, tryon_result_id: UUID
) -> bool:
    result = await db.execute(
        select(TryonResult).where(
            TryonResult.id == tryon_result_id,
            TryonResult.user_id == user_id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundException("试衣结果不存在")

    fav_result = await db.execute(
        select(FavoriteTryonResult).where(
            FavoriteTryonResult.user_id == user_id,
            FavoriteTryonResult.tryon_result_id == tryon_result_id,
        )
    )
    return fav_result.scalar_one_or_none() is not None


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


async def toggle_favorite_tryon_result(
    db: AsyncSession, user_id: UUID, tryon_result_id: UUID
) -> bool:
    result = await db.execute(
        select(TryonResult).where(
            TryonResult.id == tryon_result_id,
            TryonResult.user_id == user_id,
        )
    )
    tryon_result = result.scalar_one_or_none()
    if tryon_result is None:
        raise NotFoundException("试衣结果不存在")

    fav_result = await db.execute(
        select(FavoriteTryonResult).where(
            FavoriteTryonResult.user_id == user_id,
            FavoriteTryonResult.tryon_result_id == tryon_result_id,
        )
    )
    fav = fav_result.scalar_one_or_none()
    if fav:
        await db.delete(fav)
        await db.commit()
        return False
    else:
        await db.execute(
            insert(FavoriteTryonResult)
            .values(user_id=user_id, tryon_result_id=tryon_result_id)
            .on_conflict_do_nothing(
                index_elements=["user_id", "tryon_result_id"]
            )
        )
        await db.commit()
        return True
