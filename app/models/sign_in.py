from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class SignInRecord(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "sign_in_records"

    __table_args__ = (
        UniqueConstraint("user_id", "sign_date", name="uix_user_sign_date"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    sign_date: Mapped[date] = mapped_column(Date, index=True)
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1)
    reward_credits: Mapped[int] = mapped_column(Integer, default=0)
