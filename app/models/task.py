from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class Task(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "tasks"

    name: Mapped[str] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reward_credits: Mapped[int] = mapped_column(Integer, default=0)

    # 触发事件，例如：first_tryon, first_puzzle, first_share, daily_sign_in
    trigger_event: Mapped[str] = mapped_column(String(50), index=True)
    max_times: Mapped[int] = mapped_column(Integer, default=1)  # 每个用户最多完成次数

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)


class UserTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "user_tasks"

    __table_args__ = (
        UniqueConstraint("user_id", "task_id", name="uix_user_task"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True
    )
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    claimed_count: Mapped[int] = mapped_column(Integer, default=0)
