from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class UserFollow(Base, UUIDMixin):
    __tablename__ = "user_follows"

    follower_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    following_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(default=now_bj)

    __table_args__ = (
        UniqueConstraint(
            "follower_id", "following_id", name="uq_user_follows_follower_following"
        ),
    )
