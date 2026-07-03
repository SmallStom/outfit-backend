from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class OutfitFeedback(Base, UUIDMixin):
    __tablename__ = "outfit_feedbacks"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    outfit_id: Mapped[UUID] = mapped_column(
        ForeignKey("outfits.id", ondelete="CASCADE")
    )
    item_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(10))  # 'like' | 'dislike'
    created_at: Mapped[datetime] = mapped_column(default=now_bj)

    __table_args__ = (
        UniqueConstraint(
            "user_id", "outfit_id", "item_id", "action",
            name="uq_outfit_feedbacks_user_outfit_item_action",
        ),
    )
