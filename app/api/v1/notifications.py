from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.services.notification_service import get_user_membership_reminder

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("/membership-reminder")
async def membership_reminder(db: DbSession, user_id: CurrentUserId):
    reminder = await get_user_membership_reminder(db=db, user_id=UUID(user_id))
    return success(data=reminder)
