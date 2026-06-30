from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.credit import (
    CreditBalanceOut,
    CreditPackageOut,
    CreditTransactionOut,
)
from app.services.credit_service import (
    get_balance,
    list_credit_packages,
    list_transactions,
)

router = APIRouter(prefix="/credits", tags=["credits"])


@router.get("/balance")
async def get_credit_balance(db: DbSession, user_id: CurrentUserId):
    balance = await get_balance(db=db, user_id=UUID(user_id))
    return success(data=CreditBalanceOut.model_validate(balance).model_dump(by_alias=True))


@router.get("/transactions")
async def get_credit_transactions(
    db: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    transactions, total = await list_transactions(
        db=db, user_id=UUID(user_id), limit=limit, offset=offset
    )
    return success(
        data={
            "list": [
                CreditTransactionOut.model_validate(t).model_dump(by_alias=True)
                for t in transactions
            ],
            "total": total,
        }
    )


@router.get("/packages")
async def get_credit_packages(db: DbSession):
    packages = await list_credit_packages(db=db)
    return success(
        data=[
            CreditPackageOut.model_validate(p).model_dump(by_alias=True)
            for p in packages
        ]
    )
