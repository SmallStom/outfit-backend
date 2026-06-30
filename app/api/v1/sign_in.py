from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.sign_in import SignInCalendarItem, SignInStatusOut
from app.services.sign_in_service import (
    get_recent_calendar,
    get_today_status,
    sign_in,
)

router = APIRouter(prefix="/sign-in", tags=["sign-in"])


@router.get("/status")
async def get_sign_in_status(db: DbSession, user_id: CurrentUserId):
    status = await get_today_status(db=db, user_id=UUID(user_id))
    return success(data=SignInStatusOut.model_validate(status).model_dump(by_alias=True))


@router.post("/sign")
async def do_sign_in(db: DbSession, user_id: CurrentUserId):
    result = await sign_in(db=db, user_id=UUID(user_id))
    return success(data=SignInStatusOut.model_validate(result).model_dump(by_alias=True))


@router.get("/calendar")
async def get_sign_in_calendar(
    db: DbSession,
    user_id: CurrentUserId,
    days: Annotated[int, Query(ge=7, le=90)] = 30,
):
    calendar = await get_recent_calendar(db=db, user_id=UUID(user_id), days=days)
    return success(
        data=[
            SignInCalendarItem.model_validate(item).model_dump(by_alias=True)
            for item in calendar
        ]
    )
