from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.order import OrderCreateRequest, OrderOut
from app.services.payment_service import create_order, get_order, list_orders, mock_pay

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("")
async def create_order_endpoint(
    body: OrderCreateRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    order = await create_order(
        db=db,
        user_id=UUID(user_id),
        order_type=body.order_type,
        target_id=body.target_id,
        target_count=body.target_count,
        promo_code=body.promo_code,
    )
    return success(
        data=OrderOut.model_validate(order).model_dump(by_alias=True)
    )


@router.get("")
async def get_orders(
    db: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    orders, total = await list_orders(
        db=db, user_id=UUID(user_id), limit=limit, offset=offset
    )
    return success(
        data={
            "list": [
                OrderOut.model_validate(o).model_dump(by_alias=True)
                for o in orders
            ],
            "total": total,
        }
    )


@router.get("/{order_id}")
async def get_order_detail(
    order_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    order = await get_order(db=db, order_id=order_id, user_id=UUID(user_id))
    return success(data=OrderOut.model_validate(order).model_dump(by_alias=True))


@router.post("/{order_id}/mock-pay")
async def pay_order_mock(
    order_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    if settings.app_env == "production":
        raise ForbiddenException("模拟支付仅用于开发/测试环境")
    order = await mock_pay(db=db, order_id=order_id, user_id=UUID(user_id))
    return success(data=OrderOut.model_validate(order).model_dump(by_alias=True))
