from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.promo_code import PromoCodeValidateResponse
from app.services.promo_code_service import (
    calculate_discounted_amount,
    validate_promo_code,
)

router = APIRouter(prefix="/promo-codes", tags=["promo-codes"])


@router.get("/check")
async def check_promo_code(
    db: DbSession,
    user_id: CurrentUserId,
    code: Annotated[str, Query(min_length=1)],
    order_type: Annotated[str, Query(pattern="^(membership|credit_package)$")],
    original_amount: Annotated[int, Query(ge=0)],
):
    promo = await validate_promo_code(
        db=db,
        user_id=UUID(user_id),
        code=code,
        order_type=order_type,
        original_amount=original_amount,
    )
    discounted_amount = calculate_discounted_amount(promo, original_amount)
    return success(
        data=PromoCodeValidateResponse(
            valid=True,
            code=promo.code,
            discount_type=promo.discount_type,
            discount_value=promo.discount_value,
            original_amount=original_amount,
            discounted_amount=discounted_amount,
        ).model_dump(by_alias=True)
    )
