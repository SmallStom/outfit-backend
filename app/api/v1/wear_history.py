from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.wear_history import WearHistoryCreate
from app.services.wear_history_service import (
    build_history_list_response,
    create_history,
    list_history,
    recent_history,
)

router = APIRouter(prefix="/wear-history", tags=["wear-history"])


@router.get("")
async def get_history(
    db: DbSession,
    user_id: CurrentUserId,
    occasion: Annotated[str | None, Query()] = None,
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
):
    histories = await list_history(
        db=db,
        user_id=UUID(user_id),
        occasion=occasion,
        start_date=start_date,
    )
    data = await build_history_list_response(db, UUID(user_id), histories)
    return success(data={"list": data, "total": len(data)})


@router.get("/recent")
async def get_recent_history(
    db: DbSession,
    user_id: CurrentUserId,
    days: Annotated[int, Query(ge=1, le=365)] = 7,
):
    histories = await recent_history(db=db, user_id=UUID(user_id), days=days)
    data = await build_history_list_response(db, UUID(user_id), histories)
    return success(data={"list": data, "total": len(data)})


@router.post("")
async def add_history(
    body: WearHistoryCreate,
    db: DbSession,
    user_id: CurrentUserId,
):
    history = await create_history(db=db, user_id=UUID(user_id), data=body)
    data = await build_history_list_response(db, UUID(user_id), [history])
    return success(data=data[0])
