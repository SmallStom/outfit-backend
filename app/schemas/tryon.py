from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class TryonItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    category: str
    color: str | None = None
    image_url: str = ""


class TryonPresetItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    category: str
    color: str | None = None
    image_url: str = ""


class TryonPreset(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: str
    name: str
    occasion: str | None = None
    items: list[TryonPresetItem] = Field(default_factory=list)


class TryonGenerateRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    top_item_id: UUID | None = None
    bottom_item_id: UUID | None = None
    outer_item_id: UUID | None = None
    shoes_item_id: UUID | None = None
