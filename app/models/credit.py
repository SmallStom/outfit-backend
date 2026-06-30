from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class CreditAccount(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "credit_accounts"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )

    free_balance: Mapped[int] = mapped_column(Integer, default=0)  # 签到/赠送积分
    paid_balance: Mapped[int] = mapped_column(Integer, default=0)  # 购买积分
    total_balance: Mapped[int] = mapped_column(Integer, default=0)


class CreditTransaction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "credit_transactions"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    type: Mapped[str] = mapped_column(String(30))  # sign_in, purchase, consume, refund, expired
    amount: Mapped[int] = mapped_column(Integer)   # 正数=收入，负数=支出

    free_amount: Mapped[int] = mapped_column(Integer, default=0)  # 涉及免费积分的金额
    paid_amount: Mapped[int] = mapped_column(Integer, default=0)  # 涉及购买积分的金额

    balance_after: Mapped[int] = mapped_column(Integer)

    related_order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class CreditPackage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "credit_packages"

    name: Mapped[str] = mapped_column(String(50))
    credits: Mapped[int] = mapped_column(Integer)          # 包含积分数量
    price: Mapped[int] = mapped_column(Integer)            # 原价，单位：分
    discount_price: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 优惠价，单位：分

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
