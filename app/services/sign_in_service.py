from datetime import date, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj
from app.models.sign_in import SignInRecord
from app.services.credit_service import earn_credits


async def get_today_status(db: AsyncSession, user_id: UUID) -> dict:
    today = now_bj().date()
    result = await db.execute(
        select(SignInRecord).where(
            SignInRecord.user_id == user_id,
            SignInRecord.sign_date == today,
        )
    )
    record = result.scalar_one_or_none()

    if record:
        return {
            "signed_in": True,
            "consecutive_days": record.consecutive_days,
            "reward_credits": record.reward_credits,
        }

    # 计算今日预计奖励
    consecutive = await _get_consecutive_days(db, user_id, today)
    reward = _calculate_reward(consecutive)
    return {
        "signed_in": False,
        "consecutive_days": consecutive,
        "reward_credits": reward,
    }


async def sign_in(db: AsyncSession, user_id: UUID) -> dict:
    today = now_bj().date()

    result = await db.execute(
        select(SignInRecord).where(
            SignInRecord.user_id == user_id,
            SignInRecord.sign_date == today,
        )
    )
    if result.scalar_one_or_none():
        raise BadRequestException("今日已签到")

    consecutive = await _get_consecutive_days(db, user_id, today)
    reward = _calculate_reward(consecutive)

    record = SignInRecord(
        user_id=user_id,
        sign_date=today,
        consecutive_days=consecutive,
        reward_credits=reward,
    )
    db.add(record)
    await db.commit()

    # 发放签到积分
    expires_at = now_bj() + timedelta(days=settings.sign_in_reward_expire_days)
    await earn_credits(
        db=db,
        user_id=user_id,
        amount=reward,
        source="sign_in",
        expires_at=expires_at,
        remark=f"连续签到 {consecutive} 天",
    )

    return {
        "signed_in": True,
        "consecutive_days": consecutive,
        "reward_credits": reward,
    }


async def get_recent_calendar(
    db: AsyncSession, user_id: UUID, days: int = 30
) -> list[dict]:
    end = now_bj().date()
    start = end - timedelta(days=days - 1)
    result = await db.execute(
        select(SignInRecord).where(
            SignInRecord.user_id == user_id,
            SignInRecord.sign_date >= start,
            SignInRecord.sign_date <= end,
        ).order_by(SignInRecord.sign_date.asc())
    )
    records = {r.sign_date.isoformat(): r.reward_credits for r in result.scalars().all()}

    calendar = []
    for i in range(days):
        d = start + timedelta(days=i)
        calendar.append({
            "date": d.isoformat(),
            "signed_in": d.isoformat() in records,
            "reward_credits": records.get(d.isoformat(), 0),
        })
    return calendar


async def _get_consecutive_days(db: AsyncSession, user_id: UUID, today: date) -> int:
    yesterday = today - timedelta(days=1)
    result = await db.execute(
        select(SignInRecord).where(
            SignInRecord.user_id == user_id,
            SignInRecord.sign_date == yesterday,
        )
    )
    record = result.scalar_one_or_none()
    if record:
        return record.consecutive_days + 1
    return 1


def _calculate_reward(consecutive_days: int) -> int:
    return min(
        settings.sign_in_reward_base + (consecutive_days - 1),
        settings.sign_in_reward_max,
    )
