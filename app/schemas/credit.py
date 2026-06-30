from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import to_camel


class CreditBalanceOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    total: int
    free: int
    paid: int


class CreditTransactionOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    type: str
    amount: int
    free_amount: int
    paid_amount: int
    balance_after: int
    expires_at: datetime | None = None
    expired_at: datetime | None = None
    remark: str | None = None
    created_at: datetime


class CreditPackageOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

    id: UUID
    name: str
    credits: int
    price: int
    discount_price: int | None = None
    sort_order: int
