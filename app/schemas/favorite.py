from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class FavoritePostOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    author: str
    avatar_color: str | None = None
    title: str
    cover_color: str | None = None
    img_height: int | None = None
    like_count: int
    style: str | None = None
    favorited_at: datetime
    image_url: str = ""


class FavoriteItemOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    image_color: str | None = None
    price: int | None = None
    brand: str | None = None
    favorited_at: datetime
    image_url: str = ""


class FavoritesResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    posts: list[FavoritePostOut] = Field(default_factory=list)
    items: list[FavoriteItemOut] = Field(default_factory=list)
