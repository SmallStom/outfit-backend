from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.community import (
    CommentCreateRequest,
    CommentListResponse,
    CommentOut,
    CreatePostRequest,
    LikeResponse,
    PostDetailOut,
    PostListItem,
    PostListResponse,
)
from app.services.community_service import (
    _comment_item,
    create_comment,
    create_post,
    get_post_detail,
    list_comments,
    list_featured_posts,
    list_posts,
    style_tags,
    toggle_like,
)

router = APIRouter(prefix="/community", tags=["community"])


@router.get("/style-tags")
async def get_style_tags():
    return success(data=style_tags())


@router.get("/posts")
async def get_posts(
    db: DbSession,
    user_id: CurrentUserId,
    tab: Annotated[str, Query()] = "recommend",
    city: Annotated[str | None, Query()] = None,
    style: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    data, total = await list_posts(
        db=db,
        current_user_id=UUID(user_id),
        tab=tab,
        city=city,
        style=style,
        limit=limit,
        offset=offset,
    )
    return success(
        data=PostListResponse(
            list=[PostListItem.model_validate(row).model_dump(by_alias=True) for row in data],
            total=total,
        ).model_dump(by_alias=True)
    )


@router.get("/posts/featured")
async def get_featured_posts(
    db: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    data, total = await list_featured_posts(
        db=db, current_user_id=UUID(user_id), limit=limit, offset=offset
    )
    return success(
        data=PostListResponse(
            list=[PostListItem.model_validate(row).model_dump(by_alias=True) for row in data],
            total=total,
        ).model_dump(by_alias=True)
    )


@router.post("/posts")
async def publish_post(
    body: CreatePostRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    post = await create_post(db=db, user_id=UUID(user_id), data=body)
    return success(
        data=PostListItem.model_validate(
            {
                "id": post.id,
                "author": {"id": post.user_id, "name": post.author_name, "avatar_color": post.author_avatar_color},
                "title": post.title,
                "cover_color": post.cover_color,
                "img_height": post.img_height,
                "like_count": post.like_count,
                "is_featured": post.is_featured,
                "is_liked": False,
                "style": post.style,
                "city": post.city,
                "images": post.images,
                "content": post.content,
                "comment_count": post.comment_count,
                "tags": post.tags,
                "created_at": post.created_at,
                "image_url": post.images[0] if post.images else "",
            }
        ).model_dump(by_alias=True)
    )


@router.get("/posts/{post_id}")
async def get_post(
    post_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    data = await get_post_detail(db=db, current_user_id=UUID(user_id), post_id=post_id)
    return success(data=PostDetailOut.model_validate(data).model_dump(by_alias=True))


@router.get("/posts/{post_id}/comments")
async def get_comments(
    post_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    data, total = await list_comments(db=db, post_id=post_id, limit=limit, offset=offset)
    return success(
        data=CommentListResponse(
            list=[CommentOut.model_validate(row).model_dump(by_alias=True) for row in data],
            total=total,
        ).model_dump(by_alias=True)
    )


@router.post("/posts/{post_id}/comments")
async def add_comment(
    post_id: UUID,
    body: CommentCreateRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    comment = await create_comment(
        db=db, current_user_id=UUID(user_id), post_id=post_id, content=body.content
    )
    return success(
        data=CommentOut.model_validate(_comment_item(comment)).model_dump(by_alias=True)
    )


@router.post("/posts/{post_id}/like")
async def like_post(
    post_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    result = await toggle_like(db=db, current_user_id=UUID(user_id), post_id=post_id)
    return success(data=LikeResponse.model_validate(result).model_dump(by_alias=True))
