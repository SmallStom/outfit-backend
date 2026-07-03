from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Item(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "items"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20), index=True)
    sub_category: Mapped[str | None] = mapped_column(String(30), nullable=True)

    image_url: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_color: Mapped[str | None] = mapped_column(String(10), nullable=True)

    price: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)
    material: Mapped[str | None] = mapped_column(String(200), nullable=True)
    color: Mapped[str | None] = mapped_column(String(50), nullable=True)
    color_hex: Mapped[str | None] = mapped_column(String(10), nullable=True)
    season: Mapped[str | None] = mapped_column(String(50), nullable=True)

    care_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    care_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(200), nullable=True)

    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    wear_count: Mapped[int] = mapped_column(Integer, default=0)
    last_worn_at: Mapped[datetime | None] = mapped_column(nullable=True)

    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True, default=list
    )
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---------- 推荐系统结构化属性 ----------
    attributes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    formality: Mapped[float | None] = mapped_column(Float, nullable=True)
    femininity: Mapped[float | None] = mapped_column(Float, nullable=True)
    athletic: Mapped[float | None] = mapped_column(Float, nullable=True)
    vintage: Mapped[float | None] = mapped_column(Float, nullable=True)
    thickness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suitable_temp_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    suitable_temp_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occasion_tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True
    )
    color_hex_list: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(10)), nullable=True
    )
    keywords: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True
    )
    feature_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    feature_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    owner: Mapped["User"] = relationship("User", back_populates="items")
