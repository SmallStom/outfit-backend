from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PromoCode(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "promo_codes"

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # amount: 固定金额减免（单位：分）；percent: 百分比折扣（如 20 表示 8 折）
    discount_type: Mapped[str] = mapped_column(String(20), default="amount")  # amount / percent
    discount_value: Mapped[int] = mapped_column(Integer)

    # 适用范围
    applicable_type: Mapped[str] = mapped_column(String(30), default="all")  # all / membership / credit_package

    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 总使用次数上限
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    max_uses_per_user: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 单用户最多使用次数

    min_order_amount: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 最低订单金额（分）

    is_active: Mapped[bool] = mapped_column(default=True)


class PromoCodeUsage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "promo_code_usages"

    promo_code_id: Mapped[UUID] = mapped_column(
        ForeignKey("promo_codes.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    order_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
