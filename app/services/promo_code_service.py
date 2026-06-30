from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj
from app.models.promo_code import PromoCode, PromoCodeUsage


async def get_promo_code_by_code(db: AsyncSession, code: str) -> PromoCode | None:
    result = await db.execute(
        select(PromoCode).where(
            PromoCode.code == code,
            PromoCode.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


async def validate_promo_code(
    db: AsyncSession,
    user_id: UUID,
    code: str,
    order_type: str,
    original_amount: int,
) -> PromoCode:
    """校验优惠码是否可用，返回 PromoCode。"""
    promo = await get_promo_code_by_code(db, code)
    if promo is None:
        raise BadRequestException("优惠码不存在或已失效")

    now = now_bj()
    if promo.valid_from and promo.valid_from > now:
        raise BadRequestException("优惠码未生效")
    if promo.valid_to and promo.valid_to < now:
        raise BadRequestException("优惠码已过期")

    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise BadRequestException("优惠码使用次数已达上限")

    if promo.applicable_type != "all" and promo.applicable_type != order_type:
        raise BadRequestException("优惠码不适用于当前订单类型")

    if promo.min_order_amount is not None and original_amount < promo.min_order_amount:
        raise BadRequestException(f"订单金额未满 {promo.min_order_amount / 100} 元")

    if promo.max_uses_per_user is not None:
        user_usage = (
            await db.execute(
                select(func.count()).where(
                    PromoCodeUsage.promo_code_id == promo.id,
                    PromoCodeUsage.user_id == user_id,
                )
            )
        ).scalar() or 0
        if user_usage >= promo.max_uses_per_user:
            raise BadRequestException("您已使用该优惠码")

    return promo


def calculate_discounted_amount(promo: PromoCode, original_amount: int) -> int:
    """计算优惠后金额，单位：分。"""
    if promo.discount_type == "amount":
        return max(0, original_amount - promo.discount_value)
    elif promo.discount_type == "percent":
        # discount_value 表示减免百分比，如 20 表示减免 20%
        return max(0, int(original_amount * (100 - promo.discount_value) / 100))
    return original_amount


async def record_promo_code_usage(
    db: AsyncSession,
    promo_code_id: UUID,
    user_id: UUID,
    order_id: UUID,
) -> None:
    """记录优惠码使用并增加计数。"""
    usage = PromoCodeUsage(
        promo_code_id=promo_code_id,
        user_id=user_id,
        order_id=order_id,
    )
    db.add(usage)

    promo = await db.execute(
        select(PromoCode).where(PromoCode.id == promo_code_id).with_for_update()
    )
    promo_code = promo.scalar_one()
    promo_code.used_count += 1

    await db.commit()
