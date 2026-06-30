from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class OrderCreateRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    order_type: str = Field(..., pattern="^(membership|credit_package)$")
    target_id: UUID
    target_count: int = Field(default=1, ge=1)
    promo_code: str | None = Field(default=None, min_length=1, max_length=50)


class OrderOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    order_type: str
    target_id: UUID
    target_count: int
    amount: int
    original_amount: int
    status: str
    payment_method: str | None = None
    out_trade_no: str | None = None
    paid_at: datetime | None = None
    started_at: datetime | None = None
    expired_at: datetime | None = None
    created_at: datetime
