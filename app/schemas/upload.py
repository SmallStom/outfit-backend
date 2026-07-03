from pydantic import BaseModel, ConfigDict, Field


def to_camel(snake: str) -> str:
    parts = snake.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


class EcommerceImageCandidate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    url: str
    type: str = "main"  # main | detail


class EcommerceImagesResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    platform: str
    platform_name: str
    url: str
    images: list[EcommerceImageCandidate]


class EcommerceUrlRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)


class RemoteImageRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)


class RemoteImageResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    url: str
