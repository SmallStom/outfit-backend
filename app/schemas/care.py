from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class CareRecordCreate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    item_id: UUID
    care_type: str = Field(..., max_length=20)
    care_date: date
    notes: str | None = Field(default=None, max_length=1000)


class CareReminderItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    item_id: UUID
    item_name: str
    thumbnail_color: str | None = None
    image_url: str = ""
    last_care_date: str = ""
    wear_count: int
    alert_type: str
    alert_message: str
    care_method: str | None = None
    done: bool = False


class CareReminderGroup(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    category: str
    color: str
    care_type: str
    items: list[CareReminderItem] = Field(default_factory=list)


class CareStats(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    pending_count: int
    completed_this_month: int


class CareReminderResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    stats: CareStats
    groups: list[CareReminderGroup]
