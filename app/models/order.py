from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Order(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "orders"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    order_type: Mapped[str] = mapped_column(String(30))  # membership, credit_package
    target_id: Mapped[UUID] = mapped_column(index=True)  # tier_id or package_id
    target_count: Mapped[int] = mapped_column(Integer, default=1)  # 月数 or 包数

    amount: Mapped[int] = mapped_column(Integer)            # 实付金额，单位：分
    original_amount: Mapped[int] = mapped_column(Integer)   # 原价，单位：分

    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / paid / cancelled / refunded
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)  # wechat / mock / free
    out_trade_no: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  # 优惠码、新人价标记等
