from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.purchase_preview import (
    PurchaseAnalyzeRequest,
    PurchasePreviewListResponse,
    PurchasePreviewOut,
)
from app.services.purchase_preview_service import analyze, get_preview, history

router = APIRouter(prefix="/purchase-preview", tags=["purchase-preview"])


@router.post("/analyze")
async def analyze_purchase(
    body: PurchaseAnalyzeRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    preview = await analyze(db=db, user_id=UUID(user_id), data=body)
    return success(
        data=PurchasePreviewOut.model_validate(preview).model_dump(by_alias=True)
    )


@router.get("/history")
async def purchase_history(db: DbSession, user_id: CurrentUserId):
    previews = await history(db=db, user_id=UUID(user_id))
    return success(
        data=PurchasePreviewListResponse(
            list=[
                PurchasePreviewOut.model_validate(p).model_dump(by_alias=True)
                for p in previews
            ],
            total=len(previews),
        ).model_dump(by_alias=True)
    )


@router.get("/{preview_id}")
async def get_purchase_preview(
    preview_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    preview = await get_preview(db=db, user_id=UUID(user_id), preview_id=preview_id)
    return success(
        data=PurchasePreviewOut.model_validate(preview).model_dump(by_alias=True)
    )
