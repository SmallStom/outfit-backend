from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import to_camel


class ModelTemplateOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    name: str
    preview_image_url: str
    template_image_url: str
    slots: dict


class PuzzleGenerateRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    template_id: UUID
    item_ids: list[UUID]


class PuzzleGenerateResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    task_id: str
    status: str
    result_image_url: str | None = None


class PuzzleResultOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    template_id: UUID | None = None
    item_ids: list[UUID]
    result_image_url: str | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
