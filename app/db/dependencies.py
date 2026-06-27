from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnauthorizedException
from app.core.security import decode_access_token
from app.db.session import get_db


async def get_current_user_id(
    authorization: Annotated[str | None, Header()] = None,
) -> str:
    if authorization is None:
        raise UnauthorizedException("缺少认证信息")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise UnauthorizedException("认证格式错误")
    try:
        user_id = decode_access_token(token)
    except ValueError as exc:
        raise UnauthorizedException("登录已过期或 Token 无效") from exc
    return str(user_id)


DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUserId = Annotated[str, Depends(get_current_user_id)]
