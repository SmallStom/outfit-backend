from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.core.timezone import now_bj
from app.models.credit import CreditAccount, CreditPackage, CreditTransaction


async def get_or_create_account(db: AsyncSession, user_id: UUID) -> CreditAccount:
    result = await db.execute(
        select(CreditAccount).where(CreditAccount.user_id == user_id).with_for_update()
    )
    account = result.scalar_one_or_none()
    if account is None:
        account = CreditAccount(
            user_id=user_id,
            free_balance=0,
            paid_balance=0,
            total_balance=0,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)
    return account


async def get_balance(db: AsyncSession, user_id: UUID) -> dict:
    account = await get_or_create_account(db, user_id)
    return {
        "total": account.total_balance,
        "free": account.free_balance,
        "paid": account.paid_balance,
    }


async def earn_credits(
    db: AsyncSession,
    user_id: UUID,
    amount: int,
    source: str,
    expires_at: datetime | None = None,
    related_order_id: UUID | None = None,
    remark: str | None = None,
) -> CreditAccount:
    """增加积分。source 如 sign_in / purchase / refund / gift。"""
    if amount <= 0:
        raise BadRequestException("增加积分数量必须大于 0")

    account = await get_or_create_account(db, user_id)
    is_free = source in ("sign_in", "gift")
    if is_free:
        account.free_balance += amount
    else:
        account.paid_balance += amount
    account.total_balance = account.free_balance + account.paid_balance

    transaction = CreditTransaction(
        user_id=user_id,
        type=source,
        amount=amount,
        free_amount=amount if is_free else 0,
        paid_amount=0 if is_free else amount,
        balance_after=account.total_balance,
        expires_at=expires_at,
        related_order_id=related_order_id,
        remark=remark,
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(account)
    return account


async def consume_credits(
    db: AsyncSession,
    user_id: UUID,
    amount: int,
    feature: str,
) -> CreditAccount:
    """消费积分：优先扣除 free_balance，不足部分扣除 paid_balance。"""
    if amount <= 0:
        raise BadRequestException("消费积分数量必须大于 0")

    account = await get_or_create_account(db, user_id)
    if account.total_balance < amount:
        raise BadRequestException("积分不足")

    free_deduct = min(account.free_balance, amount)
    paid_deduct = amount - free_deduct

    account.free_balance -= free_deduct
    account.paid_balance -= paid_deduct
    account.total_balance = account.free_balance + account.paid_balance

    transaction = CreditTransaction(
        user_id=user_id,
        type="consume",
        amount=-amount,
        free_amount=-free_deduct,
        paid_amount=-paid_deduct,
        balance_after=account.total_balance,
        remark=f"使用功能: {feature}",
    )
    db.add(transaction)
    await db.commit()
    await db.refresh(account)
    return account


async def list_transactions(
    db: AsyncSession,
    user_id: UUID,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[CreditTransaction], int]:
    stmt = (
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
    )
    count_result = await db.execute(select(func.count()).select_from(stmt.subquery()))
    total = count_result.scalar() or 0
    result = await db.execute(stmt.limit(limit).offset(offset))
    return list(result.scalars().all()), total


async def expire_credits(db: AsyncSession) -> int:
    """扫描并过期已到期的积分，返回处理的账户数。

    简化逻辑：找到所有已到期且未标记为过期的正向积分流水，按 free/paid 汇总后
    从当前余额中扣除（不超过余额），并标记原流水为已过期。
    """
    now = now_bj()

    result = await db.execute(select(CreditAccount).with_for_update())
    accounts = result.scalars().all()

    expired_count = 0
    for account in accounts:
        transactions_result = await db.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == account.user_id,
                CreditTransaction.amount > 0,
                CreditTransaction.expires_at != None,
                CreditTransaction.expires_at <= now,
                CreditTransaction.expired_at == None,
            )
        )
        expired_transactions = list(transactions_result.scalars().all())
        if not expired_transactions:
            continue

        free_to_expire = sum(t.free_amount for t in expired_transactions)
        paid_to_expire = sum(t.paid_amount for t in expired_transactions)

        # 按当前余额兜底，避免过度清零
        actual_free_expire = min(free_to_expire, account.free_balance)
        actual_paid_expire = min(paid_to_expire, account.paid_balance)
        total_to_expire = actual_free_expire + actual_paid_expire

        if total_to_expire <= 0:
            # 即使无余额可扣，也标记原流水为已过期，避免重复检查
            for t in expired_transactions:
                t.expired_at = now
            continue

        account.free_balance -= actual_free_expire
        account.paid_balance -= actual_paid_expire
        account.total_balance = account.free_balance + account.paid_balance

        for t in expired_transactions:
            t.expired_at = now

        transaction = CreditTransaction(
            user_id=account.user_id,
            type="expired",
            amount=-total_to_expire,
            free_amount=-actual_free_expire,
            paid_amount=-actual_paid_expire,
            balance_after=account.total_balance,
            remark="积分过期清零",
        )
        db.add(transaction)
        expired_count += 1

    await db.commit()
    return expired_count


async def list_credit_packages(db: AsyncSession) -> list[CreditPackage]:
    result = await db.execute(
        select(CreditPackage)
        .where(CreditPackage.is_active.is_(True))
        .order_by(CreditPackage.sort_order.asc())
    )
    return list(result.scalars().all())


async def get_credit_package(db: AsyncSession, package_id: UUID) -> CreditPackage:
    result = await db.execute(
        select(CreditPackage).where(
            CreditPackage.id == package_id,
            CreditPackage.is_active.is_(True),
        )
    )
    package = result.scalar_one_or_none()
    if package is None:
        raise BadRequestException("积分包不存在或已下架")
    return package
