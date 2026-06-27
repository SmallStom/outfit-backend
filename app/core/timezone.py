from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_bj() -> datetime:
    """返回带北京时区的当前时间"""
    return datetime.now(BEIJING_TZ)


def to_bj(dt: datetime | None) -> datetime | None:
    """将 naive 或 aware 时间统一转换为北京时间"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BEIJING_TZ)
    return dt.astimezone(BEIJING_TZ)
