from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import to_camel


_DISALLOWED_URL_SCHEMES = {"javascript:", "data:", "file:", "vbscript:"}


def _validate_safe_url(value: str | None) -> str | None:
    if not value:
        return value
    lowered = value.strip().lower()
    for scheme in _DISALLOWED_URL_SCHEMES:
        if lowered.startswith(scheme):
            raise ValueError("URL 协议不合法")
    return value


class WechatLoginRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    code: str
    invite_code: str | None = Field(default=None, min_length=1, max_length=16)


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    phone: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    bio: str | None = None
    gender: str | None = None
    referral_code: str | None = None
    invited_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    nickname: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    bio: str | None = None
    gender: str | None = None

    @field_validator("avatar_url")
    @classmethod
    def _check_avatar_url(cls, value: str | None) -> str | None:
        return _validate_safe_url(value)
