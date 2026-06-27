from typing import Any


def success(data: Any | None = None, message: str = "success", code: int = 0) -> dict[str, Any]:
    """前端统一成功响应格式"""
    return {"code": code, "message": message, "data": data}
