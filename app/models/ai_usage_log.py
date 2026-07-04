from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class AIUsageLog(Base, UUIDMixin):
    """记录 AI 模型调用，用于后续计费和成本分析。"""

    __tablename__ = "ai_usage_logs"

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # attribute_extract / embedding / rerank
    action: Mapped[str] = mapped_column(String(30), index=True)
    model: Mapped[str] = mapped_column(String(50))
    cost_credits: Mapped[int] = mapped_column(Integer, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_bj)
