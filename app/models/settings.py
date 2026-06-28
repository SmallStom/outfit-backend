from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timezone import now_bj
from app.db.base import Base, UUIDMixin


class UserSettings(Base, UUIDMixin):
    __tablename__ = "user_settings"

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    notification_prefs: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {
            "outfit_recommend": True,
            "care_reminder": True,
            "community_interaction": True,
        }
    )
    privacy_prefs: Mapped[dict] = mapped_column(
        JSONB, default=lambda: {
            "city_visible": True,
            "following_list_visible": True,
        }
    )
    created_at: Mapped[datetime] = mapped_column(default=now_bj)
    updated_at: Mapped[datetime] = mapped_column(default=now_bj, onupdate=now_bj)
