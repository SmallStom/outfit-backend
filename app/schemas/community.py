from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


_MAX_TITLE_LENGTH = 200
_MAX_COMMENT_LENGTH = 1000


class Author(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    avatar_color: str | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    user_id: UUID
    user: str
    avatar_color: str | None = None
    content: str
    like_count: int
    created_at: datetime


class CommentListResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    list: list[CommentOut]
    total: int


class CommentCreateRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    content: str = Field(..., max_length=_MAX_COMMENT_LENGTH)


class PostListItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    author: Author
    title: str
    cover_color: str | None = None
    img_height: int | None = None
    like_count: int
    is_featured: bool
    is_liked: bool = False
    style: str | None = None
    city: str | None = None
    images: list[str] = Field(default_factory=list)
    content: str | None = None
    comment_count: int
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    image_url: str = ""


class PostListResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    list: list[PostListItem]
    total: int


class PostDetailOut(PostListItem):
    comments: list[CommentOut] = Field(default_factory=list)


class CreatePostRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    title: str = Field(..., max_length=_MAX_TITLE_LENGTH)
    content: str | None = Field(default=None, max_length=2000)
    images: list[str] = Field(default_factory=list)
    cover_color: str | None = Field(default=None, max_length=10)
    img_height: int | None = None
    style: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=50)
    tags: list[str] = Field(default_factory=list)


class LikeResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    is_liked: bool
    like_count: int
