from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class MembershipTier(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "membership_tiers"

    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    monthly_price: Mapped[int] = mapped_column(Integer, default=0)  # 单位：分
    yearly_price: Mapped[int] = mapped_column(Integer, default=0)   # 单位：分
    new_user_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 新人首月价，单位：分

    ai_tryon_quota: Mapped[int] = mapped_column(Integer, default=0)  # 会员期内 AI 试穿次数
    puzzle_quota: Mapped[int] = mapped_column(Integer, default=0)    # 会员期内拼图次数

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class UserMembership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_memberships"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    tier_id: Mapped[UUID] = mapped_column(
        ForeignKey("membership_tiers.id", ondelete="RESTRICT"), index=True
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    ai_tryon_used: Mapped[int] = mapped_column(Integer, default=0)
    puzzle_used: Mapped[int] = mapped_column(Integer, default=0)

    status: Mapped[str] = mapped_column(String(20), default="active")  # active / expired / cancelled
    auto_renew: Mapped[bool] = mapped_column(default=False)

    tier: Mapped["MembershipTier"] = relationship("MembershipTier", lazy="selectin")
