from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelBaseModel, to_camel


class OutfitItemEntry(CamelBaseModel):
    id: UUID
    name: str
    category: str
    image_url: str = ""
    image_color: str | None = None
    thumbnail_url: str | None = None


class OutfitBase(CamelBaseModel):
    name: str | None = None
    cover_url: str | None = None
    cover_color: str | None = None
    occasion: str | None = None
    weather: str | None = None
    is_ai_generated: bool = False
    color_scheme: list[str] | None = None


class OutfitCreate(OutfitBase):
    item_ids: list[UUID] = Field(default_factory=list)


class OutfitUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    name: str | None = None
    cover_url: str | None = None
    cover_color: str | None = None
    occasion: str | None = None
    weather: str | None = None
    is_ai_generated: bool | None = None
    color_scheme: list[str] | None = None
    item_ids: list[UUID] | None = None


class OutfitOut(OutfitBase):
    id: UUID
    items: list[OutfitItemEntry] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class OutfitListResponse(CamelBaseModel):
    list: list[OutfitOut]
    total: int


class OutfitCollectionBase(CamelBaseModel):
    name: str
    desc: str | None = None
    cover_url: str | None = None
    cover_color: str | None = None


class OutfitCollectionCreate(OutfitCollectionBase):
    item_ids: list[UUID] = Field(default_factory=list)


class OutfitCollectionUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    name: str | None = None
    desc: str | None = None
    cover_url: str | None = None
    cover_color: str | None = None
    item_ids: list[UUID] | None = None


class OutfitCollectionOut(OutfitCollectionBase):
    id: UUID
    count: int = 0
    items: list[OutfitItemEntry] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class OutfitCollectionListResponse(CamelBaseModel):
    list: list[OutfitCollectionOut]
    total: int
