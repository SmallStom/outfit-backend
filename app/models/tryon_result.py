from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, TimestampMixin, UUIDMixin


class TryonResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tryon_results"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(50))
    provider: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="highway"
    )

    # 输入图片（必须为公网可访问 URL）
    person_image_url: Mapped[str] = mapped_column(Text)
    top_garment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bottom_garment_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    outer_garment_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 阿里云异步任务
    task_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    result_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
