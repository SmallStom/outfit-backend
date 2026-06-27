from datetime import timedelta
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.timezone import now_bj

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(user_id: UUID, expires_delta: timedelta | None = None) -> str:
    """签发 JWT Access Token"""
    if expires_delta is None:
        expires_delta = timedelta(days=settings.access_token_expire_days)
    expire = now_bj() + expires_delta
    to_encode = {
        "sub": str(user_id),
        "type": "access",
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> UUID:
    """解析 JWT，返回 user_id"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "access":
            raise JWTError("invalid token type")
        user_id_str: str | None = payload.get("sub")
        if user_id_str is None:
            raise JWTError("missing subject")
        return UUID(user_id_str)
    except JWTError as exc:
        raise ValueError("invalid token") from exc


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
