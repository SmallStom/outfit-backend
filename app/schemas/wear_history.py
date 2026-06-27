from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelBaseModel, ItemEntry, to_camel


class WearHistoryCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    date: date
    weather: str | None = None
    occasion: str | None = None
    item_ids: list[UUID] = Field(default_factory=list)
    note: str | None = None


class WearHistoryOut(CamelBaseModel):
    id: UUID
    date: date
    weekday: str
    weather: str | None = None
    occasion: str | None = None
    item_ids: list[UUID]
    items: list[ItemEntry] = Field(default_factory=list)
    note: str | None = None
    created_at: datetime


class WearHistoryListResponse(CamelBaseModel):
    list: list[WearHistoryOut]
    total: int
