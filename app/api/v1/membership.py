from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.membership import MembershipTierOut, UserMembershipOut
from app.services.membership_service import get_user_membership, list_active_tiers

router = APIRouter(prefix="/membership", tags=["membership"])


@router.get("/tiers")
async def get_membership_tiers(db: DbSession):
    tiers = await list_active_tiers(db=db)
    return success(
        data=[
            MembershipTierOut.model_validate(t).model_dump(by_alias=True)
            for t in tiers
        ]
    )


@router.get("/me")
async def get_my_membership(db: DbSession, user_id: CurrentUserId):
    membership = await get_user_membership(db=db, user_id=UUID(user_id))
    if membership is None:
        return success(data=None)
    return success(
        data=UserMembershipOut.model_validate(membership).model_dump(by_alias=True)
    )
