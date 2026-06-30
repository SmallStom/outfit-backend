from pydantic import BaseModel, ConfigDict

from app.schemas.common import to_camel


class SignInStatusOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    signed_in: bool
    consecutive_days: int
    reward_credits: int


class SignInCalendarItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    date: str
    signed_in: bool
    reward_credits: int
