from datetime import date, datetime
from uuid import UUID

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class CareRecord(Base, UUIDMixin):
    __tablename__ = "care_records"

    item_id: Mapped[UUID] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    care_type: Mapped[str] = mapped_column(String(20))
    care_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=now_bj)
