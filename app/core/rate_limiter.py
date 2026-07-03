"""进程内最小限流器：按用户+路由维护最近一次请求时间。"""
from __future__ import annotations

import time
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import BadRequestException

# { "user_id:route": timestamp }
_last_call: dict[str, float] = {}


def check_rate_limit(user_id: str | UUID, route: str, cooldown_seconds: int | None = None) -> None:
    """检查用户在某路由上是否调用过于频繁。

    cooldown_seconds 为 None 时使用 settings.reco_min_interval_seconds（默认 30）。
    """
    cooldown = cooldown_seconds or getattr(settings, "reco_min_interval_seconds", 30)
    key = f"{user_id}:{route}"
    now = time.time()
    last = _last_call.get(key)
    if last is not None and (now - last) < cooldown:
        remaining = int(cooldown - (now - last))
        raise BadRequestException(f"操作太频繁，请 {remaining} 秒后再试")
    _last_call[key] = now
