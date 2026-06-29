from datetime import datetime
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

    mode: str = Field(default="fast", pattern="^(fast|premium)$")
    person_image_url: str = Field(..., min_length=1)
    top_item_id: UUID | None = None
    bottom_item_id: UUID | None = None
    outer_item_id: UUID | None = None


class TryonGenerateResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    task_id: str
    status: str


class TryonResultOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    mode: str
    status: str
    result_image_url: str | None = None
    error_message: str | None = None
    created_at: datetime
