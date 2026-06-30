from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class MembershipTierOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    name: str
    description: str | None = None
    monthly_price: int
    yearly_price: int
    new_user_price: int | None = None
    ai_tryon_quota: int
    puzzle_quota: int
    sort_order: int


class UserMembershipOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    tier: MembershipTierOut
    started_at: datetime
    expired_at: datetime
    ai_tryon_used: int
    puzzle_used: int
    status: str
