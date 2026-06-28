from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.care import (
    CareRecordCreate,
    CareReminderGroup,
    CareReminderResponse,
    CareStats,
)
from app.services.care_service import get_reminders, get_stats, mark_done

router = APIRouter(prefix="/care", tags=["care"])


@router.get("/reminders")
async def reminders(db: DbSession, user_id: CurrentUserId):
    data = await get_reminders(db=db, user_id=UUID(user_id))
    response = CareReminderResponse(
        stats=CareStats.model_validate(data["stats"]),
        groups=[CareReminderGroup.model_validate(g) for g in data["groups"]],
    )
    return success(data=response.model_dump(by_alias=True))


@router.get("/stats")
async def care_stats(db: DbSession, user_id: CurrentUserId):
    data = await get_stats(db=db, user_id=UUID(user_id))
    return success(data=CareStats.model_validate(data).model_dump(by_alias=True))


@router.post("/records")
async def create_care_record(
    db: DbSession,
    user_id: CurrentUserId,
    body: CareRecordCreate,
):
    await mark_done(db=db, user_id=UUID(user_id), item_id=body.item_id)
    return success(data={"success": True})
