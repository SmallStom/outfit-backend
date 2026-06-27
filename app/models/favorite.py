from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class FavoritePost(Base, UUIDMixin):
    __tablename__ = "favorite_posts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    post_id: Mapped[UUID] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=now_bj)

    __table_args__ = (
        UniqueConstraint("user_id", "post_id", name="uq_favorite_posts_user_post"),
    )


class FavoriteItem(Base, UUIDMixin):
    __tablename__ = "favorite_items"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=now_bj)

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_favorite_items_user_item"),
    )
