from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timezone import now_bj
from app.models.puzzle_result import PuzzleResult
from app.models.tryon_result import TryonResult
from app.services.credit_service import consume_credits, get_balance
from app.services.membership_service import check_membership_quota, deduct_membership_quota


async def can_use_tryon(db: AsyncSession, user_id: UUID) -> dict:
    """判断用户是否可以使用 AI 试穿，返回来源与成本。"""
    membership_quota = await check_membership_quota(db, user_id, "tryon")
    if membership_quota["has_quota"]:
        return {
            "allowed": True,
            "source": "membership",
            "remaining": membership_quota["remaining"],
            "cost": 0,
        }

    if await _has_free_daily_quota(db, user_id, "tryon"):
        return {
            "allowed": True,
            "source": "free_daily",
            "remaining": settings.feature_free_tryon_daily_limit - await _get_free_daily_usage(db, user_id, "tryon"),
            "cost": 0,
        }

    balance = await get_balance(db, user_id)
    cost = settings.tryon_credit_cost
    if balance["total"] >= cost:
        return {
            "allowed": True,
            "source": "credits",
            "remaining": balance["total"],
            "cost": cost,
        }

    return {
        "allowed": False,
        "source": None,
        "remaining": 0,
        "cost": cost,
    }


async def can_use_puzzle(db: AsyncSession, user_id: UUID) -> dict:
    """判断用户是否可以使用拼图，返回来源与成本。"""
    membership_quota = await check_membership_quota(db, user_id, "puzzle")
    if membership_quota["has_quota"]:
        return {
            "allowed": True,
            "source": "membership",
            "remaining": membership_quota["remaining"],
            "cost": 0,
        }

    if await _has_free_daily_quota(db, user_id, "puzzle"):
        return {
            "allowed": True,
            "source": "free_daily",
            "remaining": settings.feature_free_puzzle_daily_limit - await _get_free_daily_usage(db, user_id, "puzzle"),
            "cost": 0,
        }

    balance = await get_balance(db, user_id)
    cost = settings.puzzle_credit_cost
    if balance["total"] >= cost:
        return {
            "allowed": True,
            "source": "credits",
            "remaining": balance["total"],
            "cost": cost,
        }

    return {
        "allowed": False,
        "source": None,
        "remaining": 0,
        "cost": cost,
    }


async def deduct_for_tryon(db: AsyncSession, user_id: UUID) -> dict:
    """扣减 AI 试穿配额，返回实际来源。"""
    quota = await can_use_tryon(db, user_id)
    if not quota["allowed"]:
        return quota

    if quota["source"] == "membership":
        ok = await deduct_membership_quota(db, user_id, "tryon")
        if not ok:
            return await can_use_tryon(db, user_id)
        return {**quota, "deducted": True}

    if quota["source"] == "free_daily":
        return {**quota, "deducted": True}

    if quota["source"] == "credits":
        await consume_credits(db, user_id, quota["cost"], "tryon")
        return {**quota, "deducted": True}

    return {**quota, "deducted": False}


async def deduct_for_puzzle(db: AsyncSession, user_id: UUID) -> dict:
    """扣减拼图配额，返回实际来源。"""
    quota = await can_use_puzzle(db, user_id)
    if not quota["allowed"]:
        return quota

    if quota["source"] == "membership":
        ok = await deduct_membership_quota(db, user_id, "puzzle")
        if not ok:
            return await can_use_puzzle(db, user_id)
        return {**quota, "deducted": True}

    if quota["source"] == "free_daily":
        return {**quota, "deducted": True}

    if quota["source"] == "credits":
        await consume_credits(db, user_id, quota["cost"], "puzzle")
        return {**quota, "deducted": True}

    return {**quota, "deducted": False}


async def get_quota_summary(db: AsyncSession, user_id: UUID) -> dict:
    """返回用户额度总览（AI 试穿 + 拼图）。"""
    tryon_quota = await check_membership_quota(db, user_id, "tryon")
    puzzle_quota = await check_membership_quota(db, user_id, "puzzle")
    balance = await get_balance(db, user_id)

    return {
        "membership": {
            "tryon": tryon_quota,
            "puzzle": puzzle_quota,
        },
        "credits": balance,
        "free_daily": {
            "tryon": {
                "limit": settings.feature_free_tryon_daily_limit if settings.promotion_mode else 0,
                "used": await _get_free_daily_usage(db, user_id, "tryon") if settings.promotion_mode else 0,
            },
            "puzzle": {
                "limit": settings.feature_free_puzzle_daily_limit if settings.promotion_mode else 0,
                "used": await _get_free_daily_usage(db, user_id, "puzzle") if settings.promotion_mode else 0,
            },
        },
        "costs": {
            "tryon": settings.tryon_credit_cost,
            "puzzle": settings.puzzle_credit_cost,
        },
    }


async def _has_free_daily_quota(db: AsyncSession, user_id: UUID, feature: str) -> bool:
    if not settings.promotion_mode:
        return False
    limit = settings.feature_free_tryon_daily_limit if feature == "tryon" else settings.feature_free_puzzle_daily_limit
    if limit <= 0:
        return False
    usage = await _get_free_daily_usage(db, user_id, feature)
    return usage < limit


async def _get_free_daily_usage(db: AsyncSession, user_id: UUID, feature: str) -> int:
    today_start = now_bj().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    if feature == "tryon":
        model = TryonResult
    elif feature == "puzzle":
        model = PuzzleResult
    else:
        return 0

    result = await db.execute(
        select(func.count()).where(
            model.user_id == user_id,
            model.created_at >= today_start,
            model.created_at < today_end,
        )
    )
    return result.scalar() or 0
