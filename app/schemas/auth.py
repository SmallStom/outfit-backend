from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WechatLoginRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    openid: str
    phone: str | None = None
    nickname: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    bio: str | None = None
    gender: str | None = None
    created_at: datetime
    updated_at: datetime


class UserProfileUpdate(BaseModel):
    nickname: str | None = None
    avatar_url: str | None = None
    avatar_color: str | None = None
    bio: str | None = None
    gender: str | None = None
