from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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

    name: str | None = Field(default=None, max_length=50)
    height: float | None = None
    weight: float | None = None
    shoulder_width: float | None = None
    chest: float | None = None
    waist: float | None = None
    hip: float | None = None
    body_type: str | None = Field(default=None, max_length=30)
    body_type_label: str | None = Field(default=None, max_length=30)
    photo_url: str | None = None
    photo_color: str | None = Field(default=None, max_length=10)
    is_active: bool | None = None
    size_advice: dict | None = None
    advice: str | None = Field(default=None, max_length=500)

    @field_validator(
        "height", "weight", "shoulder_width", "chest", "waist", "hip"
    )
    @classmethod
    def _check_positive_measurement(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("身体数据必须大于 0")
        return value

    @field_validator("name", "body_type", "body_type_label", "advice")
    @classmethod
    def _check_strings(cls, value: str | None) -> str | None:
        if value is not None and len(value) == 0:
            raise ValueError("字段不能为空字符串")
        return value


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
