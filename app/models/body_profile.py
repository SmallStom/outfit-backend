from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class BodyProfile(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "body_profiles"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    height: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    weight: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    shoulder_width: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    chest: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    waist: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    hip: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)
    body_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    body_type_label: Mapped[str | None] = mapped_column(String(20), nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_color: Mapped[str | None] = mapped_column(String(10), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    size_advice: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "ix_body_profiles_user_active",
            "user_id",
            postgresql_where=(is_active.is_(True)),
            unique=True,
        ),
    )
