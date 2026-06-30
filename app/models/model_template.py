from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDMixin


class ModelTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "model_templates"

    name: Mapped[str] = mapped_column(String(50))
    preview_image_url: Mapped[str] = mapped_column(Text)    # 缩略图
    template_image_url: Mapped[str] = mapped_column(Text)   # 带透明/白色背景的模特模板底图

    # 每个 slot 描述某类衣物在模板上的相对位置与层级。
    # 采用相对坐标（0.0~1.0），运营无需针对不同尺寸模板手动计算像素：
    # {"top": {"x": 0.25, "y": 0.12, "scale": 0.50, "z": 2},
    #  "bottom": {"x": 0.25, "y": 0.42, "scale": 0.50, "z": 1}}
    # x/y 为相对模板宽/高的比例，scale 为衣物宽度占模板宽度的比例，z 控制叠放顺序。
    slots: Mapped[dict] = mapped_column(JSONB)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(default=True)
