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
    batch_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20), index=True)
    sub_category: Mapped[str | None] = mapped_column(String(30), nullable=True)

    image_url: Mapped[str] = mapped_column(Text)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_color: Mapped[str | None] = mapped_column(String(10), nullable=True)

    is_full_outfit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

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

    # ---------- Layer2: 视觉属性（V2） ----------
    silhouette: Mapped[str | None] = mapped_column(String(2), nullable=True)  # H/A/X/O/T
    visual_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 很轻-很重
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 修身-Oversize
    drape: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5
    structure: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 柔软-挺括
    visual_focus: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(20)), nullable=True
    )  # shoulder/chest/waist/hip/leg
    item_length: Mapped[str | None] = mapped_column(String(20), nullable=True)  # crop/regular/long

    # ---------- Layer3: 风格向量（V2） ----------
    style_vector: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 结构: {"minimalist":0.7, "commute":0.4, "street":0.5, ...}

    # ---------- Layer4: 搭配属性（V2） ----------
    occasion_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 结构: {"office":2, "meeting":1, "date":5, "travel":4, "daily":5, "party":3}
    season_scores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 结构: {"spring":4, "summer":5, "autumn":2, "winter":1}
    pairing_preferences: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # 结构: {"best_match": [...], "avoid": [...]}

    owner: Mapped["User"] = relationship("User", back_populates="items")
