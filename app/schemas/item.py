from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class ItemBase(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    name: str = Field(..., max_length=100)
    category: str = Field(..., max_length=20)
    sub_category: str | None = Field(default=None, max_length=30)
    image_url: str = ""
    thumbnail_url: str | None = None
    image_color: str | None = Field(default=None, max_length=10)
    price: int | None = None
    brand: str | None = Field(default=None, max_length=100)
    material: str | None = Field(default=None, max_length=200)
    color: str | None = Field(default=None, max_length=50)
    color_hex: str | None = Field(default=None, max_length=10)
    season: str | None = Field(default=None, max_length=50)
    care_method: str | None = Field(default=None, max_length=20)
    care_detail: str | None = None
    occasion: str | None = Field(default=None, max_length=200)
    purchase_date: date | None = None
    tags: list[str] | None = Field(default_factory=list)


class ItemCreate(ItemBase):
    image: str | None = None


class ItemUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=20)
    sub_category: str | None = Field(default=None, max_length=30)
    image_url: str | None = None
    thumbnail_url: str | None = None
    image_color: str | None = Field(default=None, max_length=10)
    price: int | None = None
    brand: str | None = Field(default=None, max_length=100)
    material: str | None = Field(default=None, max_length=200)
    color: str | None = Field(default=None, max_length=50)
    color_hex: str | None = Field(default=None, max_length=10)
    season: str | None = Field(default=None, max_length=50)
    care_method: str | None = Field(default=None, max_length=20)
    care_detail: str | None = None
    occasion: str | None = Field(default=None, max_length=200)
    purchase_date: date | None = None
    tags: list[str] | None = None


class ItemOut(ItemBase):
    id: UUID
    wear_count: int
    last_worn_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ItemListResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    list: list[ItemOut]
    total: int


class WearRecordResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    success: bool = True
    wear_count: int
    last_worn_at: datetime | None = None
