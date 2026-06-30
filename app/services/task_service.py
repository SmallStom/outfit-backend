import logging
from datetime import timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.timezone import now_bj
from app.models.task import Task, UserTask
from app.services.credit_service import earn_credits

logger = logging.getLogger(__name__)


async def list_user_tasks(db: AsyncSession, user_id: UUID) -> list[dict]:
    """列出当前用户的任务及完成/领取状态。"""
    tasks_result = await db.execute(
        select(Task).where(Task.is_active.is_(True)).order_by(Task.sort_order.asc())
    )
    tasks = list(tasks_result.scalars().all())

    task_ids = [t.id for t in tasks]
    user_tasks_result = await db.execute(
        select(UserTask).where(
            UserTask.user_id == user_id,
            UserTask.task_id.in_(task_ids),
        )
    )
    user_task_map = {ut.task_id: ut for ut in user_tasks_result.scalars().all()}

    result = []
    for task in tasks:
        ut = user_task_map.get(task.id)
        completed = ut.completed_count if ut else 0
        claimed = ut.claimed_count if ut else 0
        result.append({
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "reward_credits": task.reward_credits,
            "trigger_event": task.trigger_event,
            "max_times": task.max_times,
            "completed_count": completed,
            "claimed_count": claimed,
            "claimable_count": min(completed - claimed, task.max_times - claimed),
        })
    return result


async def complete_task(db: AsyncSession, user_id: UUID, trigger_event: str) -> None:
    """根据触发事件完成任务计数，处理并发冲突。"""
    tasks_result = await db.execute(
        select(Task).where(
            Task.trigger_event == trigger_event,
            Task.is_active.is_(True),
        )
    )
    tasks = list(tasks_result.scalars().all())
    if not tasks:
        return

    for task in tasks:
        user_task_result = await db.execute(
            select(UserTask).where(
                UserTask.user_id == user_id,
                UserTask.task_id == task.id,
            )
        )
        user_task = user_task_result.scalar_one_or_none()
        if user_task is None:
            user_task = UserTask(user_id=user_id, task_id=task.id, completed_count=0, claimed_count=0)
            db.add(user_task)

        if user_task.completed_count < task.max_times:
            user_task.completed_count += 1

        try:
            await db.commit()
        except IntegrityError:
            # 并发冲突：回滚后重新获取已有记录并更新
            await db.rollback()
            logger.warning("任务完成并发冲突，user=%s task=%s", user_id, task.id)
            retry_result = await db.execute(
                select(UserTask).where(
                    UserTask.user_id == user_id,
                    UserTask.task_id == task.id,
                )
            )
            existing = retry_result.scalar_one_or_none()
            if existing and existing.completed_count < task.max_times:
                existing.completed_count += 1
                await db.commit()


async def claim_task_reward(db: AsyncSession, user_id: UUID, task_id: UUID) -> int:
    """领取任务奖励，返回领取的积分数。"""
    task_result = await db.execute(
        select(Task).where(Task.id == task_id, Task.is_active.is_(True))
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise NotFoundException("任务不存在或已下架")

    user_task_result = await db.execute(
        select(UserTask).where(
            UserTask.user_id == user_id,
            UserTask.task_id == task_id,
        )
    )
    user_task = user_task_result.scalar_one_or_none()
    if user_task is None or user_task.claimed_count >= user_task.completed_count:
        raise BadRequestException("暂无可领取奖励")

    if user_task.claimed_count >= task.max_times:
        raise BadRequestException("该任务奖励已达上限")

    user_task.claimed_count += 1
    reward = task.reward_credits

    expires_at = now_bj() + timedelta(days=settings.sign_in_reward_expire_days)
    await earn_credits(
        db=db,
        user_id=user_id,
        amount=reward,
        source="gift",
        expires_at=expires_at,
        remark=f"完成任务：{task.name}",
    )

    await db.commit()
    return reward
