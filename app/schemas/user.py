from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import to_camel


MAX_PREFS_STRING_LEN = 200


def _validate_prefs_dict(value: dict | None) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("必须是 JSON 对象")
    if len(value) > 20:
        raise ValueError("设置项过多")
    for k, v in value.items():
        if not isinstance(k, str):
            raise ValueError("设置键必须是字符串")
        if isinstance(v, str) and len(v) > MAX_PREFS_STRING_LEN:
            raise ValueError(f"设置值 {k} 过长")
        if not isinstance(v, (str, int, float, bool)) and v is not None:
            raise ValueError(f"设置值 {k} 类型不合法")
    return value


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

    @field_validator("notification_prefs", "privacy_prefs")
    @classmethod
    def _check_prefs(cls, value: dict | None) -> dict | None:
        return _validate_prefs_dict(value)
