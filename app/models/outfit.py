from datetime import datetime
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Outfit(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outfits"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    occasion: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weather: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_ai_generated: Mapped[bool] = mapped_column(default=False)
    color_scheme: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(10)), nullable=True
    )

    items: Mapped[list["OutfitItem"]] = relationship(
        "OutfitItem",
        back_populates="outfit",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="OutfitItem.sort_order",
    )


class OutfitItem(Base, UUIDMixin):
    __tablename__ = "outfit_items"

    outfit_id: Mapped[UUID] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    outfit: Mapped["Outfit"] = relationship("Outfit", back_populates="items")
    item: Mapped["Item"] = relationship("Item", lazy="selectin")

    __table_args__ = (
        UniqueConstraint(
            "outfit_id", "item_id", name="uq_outfit_items_outfit_item"
        ),
    )


class OutfitCollection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "outfit_collections"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    cover_color: Mapped[str | None] = mapped_column(String(10), nullable=True)

    items: Mapped[list["OutfitCollectionItem"]] = relationship(
        "OutfitCollectionItem",
        back_populates="collection",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="OutfitCollectionItem.sort_order",
    )


class OutfitCollectionItem(Base, UUIDMixin):
    __tablename__ = "outfit_collection_items"

    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("outfit_collections.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    collection: Mapped["OutfitCollection"] = relationship(
        "OutfitCollection", back_populates="items"
    )
    item: Mapped["Item"] = relationship("Item", lazy="selectin")

    __table_args__ = (
        UniqueConstraint(
            "collection_id", "item_id", name="uq_outfit_collection_items_collection_item"
        ),
    )
