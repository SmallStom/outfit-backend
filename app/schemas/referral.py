from pydantic import BaseModel, ConfigDict

from app.schemas.common import to_camel


class ReferralInfoOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    referral_code: str
    invited_count: int
