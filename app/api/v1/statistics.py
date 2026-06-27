from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.statistics import (
    CostPerWearItem,
    CostPerWearListResponse,
    IdleItem,
    IdleListResponse,
    StatsOverview,
)
from app.services.statistics_service import (
    category_distribution,
    cost_per_wear,
    idle_items,
    overview,
)

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get("/overview")
async def get_overview(db: DbSession, user_id: CurrentUserId):
    data = await overview(db=db, user_id=UUID(user_id))
    return success(data=StatsOverview.model_validate(data).model_dump(by_alias=True))


@router.get("/category")
async def get_category(db: DbSession, user_id: CurrentUserId):
    data = await category_distribution(db=db, user_id=UUID(user_id))
    return success(data=data)


@router.get("/idle")
async def get_idle(db: DbSession, user_id: CurrentUserId):
    data = await idle_items(db=db, user_id=UUID(user_id))
    return success(
        data=IdleListResponse(
            list=[IdleItem.model_validate(row).model_dump(by_alias=True) for row in data],
            total=len(data),
        ).model_dump(by_alias=True)
    )


@router.get("/cost-per-wear")
async def get_cost_per_wear(db: DbSession, user_id: CurrentUserId):
    data = await cost_per_wear(db=db, user_id=UUID(user_id))
    return success(
        data=CostPerWearListResponse(
            list=[CostPerWearItem.model_validate(row).model_dump(by_alias=True) for row in data],
            total=len(data),
        ).model_dump(by_alias=True)
    )
