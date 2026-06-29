import hashlib
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.post import Comment, Post, PostLike
from app.models.user import User
from app.schemas.community import CreatePostRequest

_STYLE_TAGS = ["极简", "复古", "通勤", "街头", "甜酷", "法式", "优雅", "休闲"]


def _avatar_color(user: User) -> str:
    if user.avatar_color:
        return user.avatar_color
    palette = [
        "#667eea", "#764ba2", "#f093fb", "#4facfe", "#43e97b",
        "#fa709a", "#30cfd0", "#a8edea", "#ffd1ff", "#5ee7df",
        "#c471f5", "#f6d365", "#84fab0", "#8fd3f4", "#fccb90", "#d4fc79",
    ]
    idx = int(hashlib.md5(str(user.id).encode()).hexdigest()[:4], 16) % len(palette)
    return palette[idx]


def _author(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.nickname or f"用户{str(user.id)[:4]}",
        "avatar_color": _avatar_color(user),
    }


async def _get_user(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    return user


async def _liked_post_ids(
    db: AsyncSession, user_id: UUID, post_ids: list[UUID]
) -> set[UUID]:
    if not post_ids:
        return set()
    result = await db.execute(
        select(PostLike.post_id).where(
            PostLike.user_id == user_id,
            PostLike.post_id.in_(post_ids),
        )
    )
    return set(row[0] for row in result.all())


def _post_item(
    post: Post, user: User, liked_set: set[UUID]
) -> dict:
    return {
        "id": post.id,
        "author": _author(user),
        "title": post.title,
        "cover_color": post.cover_color,
        "img_height": post.img_height,
        "like_count": post.like_count,
        "is_featured": post.is_featured,
        "is_liked": post.id in liked_set,
        "style": post.style,
        "city": post.city,
        "images": post.images,
        "content": post.content,
        "comment_count": post.comment_count,
        "tags": post.tags,
        "created_at": post.created_at,
        "image_url": post.images[0] if post.images else "",
    }


def _comment_item(comment: Comment) -> dict:
    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "user": comment.user_name or "匿名用户",
        "avatar_color": comment.avatar_color,
        "content": comment.content,
        "like_count": comment.like_count,
        "created_at": comment.created_at,
    }


async def list_posts(
    db: AsyncSession,
    current_user_id: UUID,
    tab: str,
    city: str | None,
    style: str | None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    if tab == "recommend":
        stmt = select(Post)
    elif tab == "follow":
        # 关注功能暂未实现，先返回当前用户自己的帖子
        stmt = select(Post).where(Post.user_id == current_user_id)
    elif tab == "city" and city:
        stmt = select(Post).where(Post.city.ilike(city.strip()))
    elif tab == "style" and style:
        stmt = select(Post).where(Post.style == style.strip())
    else:
        stmt = select(Post)

    stmt = stmt.order_by(Post.is_featured.desc(), Post.created_at.desc())

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    stmt = stmt.limit(limit).offset(offset)
    result = await db.execute(stmt)
    posts = list(result.scalars().all())

    user_ids = [post.user_id for post in posts]
    users = {}
    if user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u for u in user_result.scalars().all()}

    liked_set = await _liked_post_ids(db, current_user_id, [p.id for p in posts])

    data = []
    for post in posts:
        user = users.get(post.user_id)
        if user is None:
            continue
        data.append(_post_item(post, user, liked_set))

    return data, total


async def get_post_detail(
    db: AsyncSession, current_user_id: UUID, post_id: UUID
) -> dict:
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise NotFoundException("帖子不存在")

    user = await _get_user(db, post.user_id)
    liked_set = await _liked_post_ids(db, current_user_id, [post.id])

    comment_result = await db.execute(
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    comments = [_comment_item(c) for c in comment_result.scalars().all()]

    data = _post_item(post, user, liked_set)
    data["comments"] = comments
    return data


async def toggle_like(
    db: AsyncSession, current_user_id: UUID, post_id: UUID
) -> dict:
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise NotFoundException("帖子不存在")

    like_result = await db.execute(
        select(PostLike).where(
            PostLike.user_id == current_user_id,
            PostLike.post_id == post_id,
        )
    )
    like = like_result.scalar_one_or_none()

    if like:
        await db.delete(like)
        is_liked = False
    else:
        await db.execute(
            insert(PostLike)
            .values(user_id=current_user_id, post_id=post_id)
            .on_conflict_do_nothing(
                index_elements=["user_id", "post_id"]
            )
        )
        is_liked = True

    # 重新计算点赞数，避免并发下的计数漂移
    count_result = await db.execute(
        select(func.count(PostLike.id)).where(PostLike.post_id == post_id)
    )
    post.like_count = count_result.scalar() or 0
    await db.commit()
    await db.refresh(post)
    return {"is_liked": is_liked, "like_count": post.like_count}


async def create_post(
    db: AsyncSession, user_id: UUID, data: CreatePostRequest
) -> Post:
    user = await _get_user(db, user_id)
    post = Post(
        user_id=user_id,
        author_name=_author(user)["name"],
        author_avatar_color=_avatar_color(user),
        title=data.title,
        content=data.content,
        images=data.images,
        cover_color=data.cover_color,
        img_height=data.img_height,
        style=data.style,
        city=data.city,
        tags=data.tags,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


async def list_featured_posts(
    db: AsyncSession,
    current_user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    stmt = (
        select(Post)
        .where(Post.is_featured.is_(True))
        .order_by(Post.created_at.desc())
    )

    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(stmt.limit(limit).offset(offset))
    posts = list(result.scalars().all())

    user_ids = [post.user_id for post in posts]
    users = {}
    if user_ids:
        user_result = await db.execute(select(User).where(User.id.in_(user_ids)))
        users = {u.id: u for u in user_result.scalars().all()}

    liked_set = await _liked_post_ids(db, current_user_id, [p.id for p in posts])

    data = []
    for post in posts:
        user = users.get(post.user_id)
        if user is None:
            continue
        data.append(_post_item(post, user, liked_set))

    return data, total


async def create_comment(
    db: AsyncSession, current_user_id: UUID, post_id: UUID, content: str
) -> Comment:
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    post = post_result.scalar_one_or_none()
    if post is None:
        raise NotFoundException("帖子不存在")

    user = await _get_user(db, current_user_id)
    comment = Comment(
        post_id=post_id,
        user_id=current_user_id,
        user_name=_author(user)["name"],
        avatar_color=_avatar_color(user),
        content=content,
    )
    db.add(comment)
    post.comment_count = post.comment_count + 1
    await db.commit()
    await db.refresh(comment)
    return comment


async def list_comments(
    db: AsyncSession, post_id: UUID, limit: int = 50, offset: int = 0
) -> tuple[list[dict], int]:
    post_result = await db.execute(select(Post).where(Post.id == post_id))
    if post_result.scalar_one_or_none() is None:
        raise NotFoundException("帖子不存在")

    stmt = (
        select(Comment)
        .where(Comment.post_id == post_id)
        .order_by(Comment.created_at.asc())
    )
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0

    result = await db.execute(stmt.limit(limit).offset(offset))
    comments = [_comment_item(c) for c in result.scalars().all()]
    return comments, total


def style_tags() -> list[str]:
    return _STYLE_TAGS
