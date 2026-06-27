from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class PurchasePreview(Base, UUIDMixin):
    __tablename__ = "purchase_previews"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_image: Mapped[str | None] = mapped_column(Text, nullable=True)
    item_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estimated_price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggested_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_per_wear: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    similar_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suggestions: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_bj)
