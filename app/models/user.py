from datetime import datetime
from uuid import UUID

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timezone import now_bj
from app.db.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "users"

    openid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(nullable=True)
    avatar_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bio: Mapped[str | None] = mapped_column(nullable=True)
    gender: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Membership & referral
    is_new_user: Mapped[bool] = mapped_column(Boolean, default=True)
    referral_code: Mapped[str | None] = mapped_column(String(16), unique=True, nullable=True, index=True)
    invited_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    items: Mapped[list["Item"]] = relationship(
        "Item", back_populates="owner", lazy="selectin"
    )
