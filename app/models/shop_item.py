from datetime import datetime

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ShopItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "shop_items"

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

    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True, default=list
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)

    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
