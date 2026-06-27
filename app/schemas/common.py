from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class CamelBaseModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ItemEntry(CamelBaseModel):
    """搭配/穿搭历史中引用的单品摘要"""

    id: UUID
    name: str
    category: str
    image_url: str = ""
    image_color: str | None = None
    thumbnail_url: str | None = None
