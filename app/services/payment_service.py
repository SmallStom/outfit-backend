from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.timezone import now_bj
from app.models.credit import CreditPackage
from app.models.membership import MembershipTier
from app.models.order import Order
from app.models.user import User
from app.services.credit_service import earn_credits
from app.services.membership_service import activate_membership
from app.services.promo_code_service import (
    calculate_discounted_amount,
    record_promo_code_usage,
    validate_promo_code,
)
from app.services.referral_service import reward_inviter_on_first_purchase


async def create_order(
    db: AsyncSession,
    user_id: UUID,
    order_type: str,
    target_id: UUID,
    target_count: int = 1,
    payment_method: str = "wechat",
    promo_code: str | None = None,
) -> Order:
    """创建待支付订单，支持优惠码抵扣。"""
    if order_type not in ("membership", "credit_package"):
        raise BadRequestException("订单类型错误")
    if target_count < 1:
        raise BadRequestException("购买数量必须大于 0")

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")

    if order_type == "membership":
        tier_result = await db.execute(
            select(MembershipTier).where(
                MembershipTier.id == target_id,
                MembershipTier.is_active.is_(True),
            )
        )
        tier = tier_result.scalar_one_or_none()
        if tier is None:
            raise NotFoundException("会员档位不存在或已下架")

        # 新人价仅首月有效
        if user.is_new_user and target_count == 1 and tier.new_user_price is not None:
            unit_price = tier.new_user_price
        else:
            unit_price = tier.monthly_price
        original_price = tier.monthly_price * target_count

    elif order_type == "credit_package":
        package_result = await db.execute(
            select(CreditPackage).where(
                CreditPackage.id == target_id,
                CreditPackage.is_active.is_(True),
            )
        )
        package = package_result.scalar_one_or_none()
        if package is None:
            raise NotFoundException("积分包不存在或已下架")

        unit_price = package.discount_price if package.discount_price is not None else package.price
        original_price = package.price * target_count

    amount = unit_price * target_count

    applied_promo_id = None
    if promo_code:
        promo = await validate_promo_code(
            db=db,
            user_id=user_id,
            code=promo_code,
            order_type=order_type,
            original_amount=amount,
        )
        amount = calculate_discounted_amount(promo, amount)
        applied_promo_id = promo.id

    order = Order(
        user_id=user_id,
        order_type=order_type,
        target_id=target_id,
        target_count=target_count,
        amount=amount,
        original_amount=original_price,
        status="pending",
        payment_method=payment_method,
        out_trade_no=_generate_out_trade_no(),
        extra_metadata={
            "is_new_user_price": user.is_new_user and order_type == "membership",
            "promo_code_id": str(applied_promo_id) if applied_promo_id else None,
        },
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def get_order(db: AsyncSession, order_id: UUID, user_id: UUID | None = None) -> Order:
    stmt = select(Order).where(Order.id == order_id)
    if user_id:
        stmt = stmt.where(Order.user_id == user_id)
    result = await db.execute(stmt)
    order = result.scalar_one_or_none()
    if order is None:
        raise NotFoundException("订单不存在")
    return order


async def list_orders(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Order], int]:
    from sqlalchemy import func

    stmt = (
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
    )
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all()), total


async def mock_pay(db: AsyncSession, order_id: UUID, user_id: UUID) -> Order:
    """模拟支付成功（仅用于开发/测试）。"""
    order = await get_order(db, order_id, user_id)
    if order.status != "pending":
        raise BadRequestException("订单状态不正确")

    order.status = "paid"
    order.payment_method = "mock"
    order.paid_at = now_bj()
    await db.commit()

    await fulfill_order(db, order)
    await _record_promo_usage_if_any(db, order)
    return order


async def handle_payment_callback(
    db: AsyncSession, out_trade_no: str, status: str
) -> Order:
    """支付回调通用处理。"""
    result = await db.execute(select(Order).where(Order.out_trade_no == out_trade_no))
    order = result.scalar_one_or_none()
    if order is None:
        raise NotFoundException("订单不存在")
    if order.status != "pending":
        return order

    if status == "paid":
        order.status = "paid"
        order.paid_at = now_bj()
        await db.commit()
        await fulfill_order(db, order)
        await _record_promo_usage_if_any(db, order)
    elif status == "failed":
        order.status = "cancelled"
        await db.commit()

    return order


async def fulfill_order(db: AsyncSession, order: Order) -> None:
    """根据订单类型开通会员或发放积分。"""
    now = now_bj()

    if order.order_type == "membership":
        await activate_membership(
            db=db,
            user_id=order.user_id,
            tier_id=order.target_id,
            duration_months=order.target_count,
        )
        # 首次购买会员后取消新人价资格
        user_result = await db.execute(select(User).where(User.id == order.user_id))
        user = user_result.scalar_one_or_none()
        if user and user.is_new_user:
            user.is_new_user = False
        order.started_at = now
        order.expired_at = now + timedelta(days=30 * order.target_count)

    elif order.order_type == "credit_package":
        package_result = await db.execute(
            select(CreditPackage).where(CreditPackage.id == order.target_id)
        )
        package = package_result.scalar_one_or_none()
        if package is None:
            raise BadRequestException("积分包不存在")
        total_credits = package.credits * order.target_count
        expires_at = now + timedelta(days=settings.credit_purchase_expire_days)
        await earn_credits(
            db=db,
            user_id=order.user_id,
            amount=total_credits,
            source="purchase",
            expires_at=expires_at,
            related_order_id=order.id,
            remark=f"购买积分包 {package.name} x{order.target_count}",
        )

    # 首次购买后给邀请人发放奖励
    user_result = await db.execute(select(User).where(User.id == order.user_id))
    user = user_result.scalar_one_or_none()
    if user:
        # 判断是否为首次成功支付订单
        paid_count = (
            await db.execute(
                select(func.count()).where(
                    Order.user_id == order.user_id,
                    Order.status == "paid",
                    Order.id != order.id,
                )
            )
        ).scalar() or 0
        if paid_count == 0:
            await reward_inviter_on_first_purchase(db=db, user=user)

    await db.commit()


async def _record_promo_usage_if_any(db: AsyncSession, order: Order) -> None:
    """如果订单使用了优惠码，记录使用并增加计数。"""
    meta = order.extra_metadata or {}
    promo_code_id_str = meta.get("promo_code_id")
    if not promo_code_id_str:
        return
    try:
        promo_code_id = UUID(promo_code_id_str)
    except ValueError:
        return
    await record_promo_code_usage(
        db=db,
        promo_code_id=promo_code_id,
        user_id=order.user_id,
        order_id=order.id,
    )


def _generate_out_trade_no() -> str:
    """生成商户订单号。"""
    now = now_bj()
    return f"OUT{now.strftime('%Y%m%d%H%M%S')}{now.microsecond:06d}"
