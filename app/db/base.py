from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.timezone import now_bj


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""

    type_annotation_map = {
        datetime: DateTime(timezone=True),
    }


class UUIDMixin:
    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_bj,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=now_bj,
        onupdate=now_bj,
        server_default=func.now(),
    )
