from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import CamelBaseModel, to_camel


class BodyProfileBase(CamelBaseModel):
    name: str = Field(..., max_length=50)
    height: float | None = Field(default=None, gt=0, le=300)
    weight: float | None = Field(default=None, gt=0, le=500)
    shoulder_width: float | None = Field(default=None, gt=0, le=200)
    chest: float | None = Field(default=None, gt=0, le=200)
    waist: float | None = Field(default=None, gt=0, le=200)
    hip: float | None = Field(default=None, gt=0, le=200)
    body_type: str | None = Field(default=None, max_length=30)
    body_type_label: str | None = Field(default=None, max_length=30)
    photo_url: str | None = None
    photo_color: str | None = Field(default=None, max_length=10)
    is_active: bool = False
    size_advice: dict | None = None
    advice: str | None = Field(default=None, max_length=500)


class BodyProfileCreate(BodyProfileBase):
    pass


class BodyProfileUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    name: str | None = None
    height: float | None = None
    weight: float | None = None
    shoulder_width: float | None = None
    chest: float | None = None
    waist: float | None = None
    hip: float | None = None
    body_type: str | None = None
    body_type_label: str | None = None
    photo_url: str | None = None
    photo_color: str | None = None
    is_active: bool | None = None
    size_advice: dict | None = None
    advice: str | None = None


class BodyProfileOut(BodyProfileBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class BodyProfileListResponse(CamelBaseModel):
    list: list[BodyProfileOut]
    total: int


class BodyType(CamelBaseModel):
    key: str
    label: str
    desc: str


class BodyTypeListResponse(CamelBaseModel):
    list: list[BodyType]
