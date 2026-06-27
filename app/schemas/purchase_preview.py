from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import to_camel


class PurchaseAnalyzeRequest(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    item_name: str | None = None
    estimated_price: int | None = None
    category: str | None = None
    color: str | None = None
    image_url: str | None = None
    source_url: str | None = None


class PurchaseMatchDetails(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    color_match: int
    style_match: int
    season_match: int
    occasion_match: int


class PurchaseSuggestion(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    name: str
    image_color: str | None = None
    image_url: str = ""
    match_score: int


class PurchasePreviewOut(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    id: UUID
    item_name: str | None = None
    estimated_price: int | None = None
    match_rate: int | None = None
    suggested_count: int | None = None
    cost_per_wear: int | None = None
    status: str | None = None
    hint: str | None = None
    thumbnail_color: str | None = None
    image_url: str | None = None
    match_details: PurchaseMatchDetails | None = None
    similar_items: int | None = None
    suggestions: list[PurchaseSuggestion] = Field(default_factory=list)
    created_at: datetime


class PurchasePreviewListResponse(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    list: list[PurchasePreviewOut]
    total: int
