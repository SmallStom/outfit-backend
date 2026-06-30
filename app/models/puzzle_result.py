from uuid import UUID

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class PuzzleResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "puzzle_results"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    template_id: Mapped[UUID] = mapped_column(
        ForeignKey("model_templates.id", ondelete="SET NULL"), nullable=True, index=True
    )

    item_ids: Mapped[list[UUID]] = mapped_column(JSONB)
    cutout_image_urls: Mapped[dict] = mapped_column(JSONB, default=dict)

    result_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending / succeeded / failed
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
