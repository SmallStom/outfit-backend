"""AI 调用消费记录工具。"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_usage_log import AIUsageLog


async def log_ai_usage(
    db: AsyncSession,
    *,
    user_id: UUID | None,
    action: str,
    model: str,
    cost_credits: int = 0,
    metadata: dict | None = None,
) -> None:
    """记录一次 AI 调用。后续计费可直接按 action/user_id 汇总。"""
    log = AIUsageLog(
        user_id=user_id,
        action=action,
        model=model,
        cost_credits=cost_credits,
        metadata_=metadata or {},
    )
    db.add(log)
    await db.commit()
