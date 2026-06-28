from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class UserStats(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    item_count: int
    outfit_count: int
    outfit_collection_count: int
    like_received_count: int
    followers_count: int
    following_count: int


class UserListItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    nickname: str
    avatar_url: str | None = None
    avatar_color: str | None = None


class UserSettingsOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    notification_prefs: dict = Field(default_factory=dict)
    privacy_prefs: dict = Field(default_factory=dict)


class UserSettingsUpdate(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    notification_prefs: dict | None = None
    privacy_prefs: dict | None = None
