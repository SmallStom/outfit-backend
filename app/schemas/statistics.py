from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class StatsOverview(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    total_value: int
    total_count: int
    monthly_cost: int
    avg_cost_per_wear: int
    top_brand: str | None = None


class CategoryStats(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    category: str
    label: str
    percent: int
    count: int
    color: str
    value: int


class IdleItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    thumbnail_color: str | None = None
    image_url: str = ""
    idle_days: int
    price: int | None = None
    purchase_date: str | None = None


class CostPerWearItem(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    rank: int
    name: str
    cost: int
    percent: int
    brand: str | None = None
    wear_count: int


class IdleListResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    list: list[IdleItem]
    total: int


class CostPerWearListResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    list: list[CostPerWearItem]
    total: int
