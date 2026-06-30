from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.models.user import User
from app.schemas.referral import ReferralInfoOut
from app.services.referral_service import ensure_referral_code

router = APIRouter(prefix="/referral", tags=["referral"])


@router.get("/info")
async def get_referral_info(db: DbSession, user_id: CurrentUserId):
    result = await db.execute(select(User).where(User.id == UUID(user_id)))
    user = result.scalar_one_or_none()

    code = await ensure_referral_code(db=db, user=user)

    invited_count = (
        await db.execute(
            select(func.count()).where(User.invited_by == UUID(user_id))
        )
    ).scalar() or 0

    return success(
        data=ReferralInfoOut(
            referral_code=code,
            invited_count=invited_count,
        ).model_dump(by_alias=True)
    )
