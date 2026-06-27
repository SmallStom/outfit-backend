from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    """业务异常基类"""

    def __init__(self, code: int, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class BadRequestException(AppException):
    def __init__(self, message: str = "参数错误"):
        super().__init__(code=1001, message=message, status_code=400)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "登录已过期"):
        super().__init__(code=1002, message=message, status_code=401)


class ForbiddenException(AppException):
    def __init__(self, message: str = "权限不足"):
        super().__init__(code=1003, message=message, status_code=403)


class NotFoundException(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(code=2001, message=message, status_code=404)


class AIException(AppException):
    def __init__(self, message: str = "AI 分析失败", timeout: bool = False):
        super().__init__(
            code=3002 if timeout else 3001,
            message=message,
            status_code=500,
        )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "data": None},
    )
