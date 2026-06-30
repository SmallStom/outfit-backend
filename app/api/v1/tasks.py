from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.services.task_service import claim_task_reward, list_user_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
async def get_tasks(db: DbSession, user_id: CurrentUserId):
    tasks = await list_user_tasks(db=db, user_id=UUID(user_id))
    return success(data=tasks)


@router.post("/{task_id}/claim")
async def claim_task(db: DbSession, user_id: CurrentUserId, task_id: UUID):
    reward = await claim_task_reward(db=db, user_id=UUID(user_id), task_id=task_id)
    return success(data={"reward_credits": reward})
