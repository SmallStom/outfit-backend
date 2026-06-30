from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import to_camel


class PromoCodeOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    code: str
    description: str | None = None
    discount_type: str
    discount_value: int
    applicable_type: str
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    min_order_amount: int | None = None


class PromoCodeValidateRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    code: str
    order_type: str
    original_amount: int


class PromoCodeValidateResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    valid: bool
    code: str
    discount_type: str
    discount_value: int
    original_amount: int
    discounted_amount: int
