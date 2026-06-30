from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.puzzle import (
    ModelTemplateOut,
    PuzzleGenerateRequest,
    PuzzleGenerateResponse,
    PuzzleResultOut,
)
from app.services.puzzle_service import (
    generate_puzzle,
    get_puzzle_result,
    list_puzzle_results,
    list_templates,
)
from app.services.share_service import share_puzzle_result

router = APIRouter(prefix="/puzzle", tags=["puzzle"])


@router.get("/templates")
async def get_puzzle_templates(db: DbSession):
    templates = await list_templates(db=db)
    return success(
        data=[
            ModelTemplateOut.model_validate(t).model_dump(by_alias=True)
            for t in templates
        ]
    )


@router.post("/generate")
async def puzzle_generate(
    body: PuzzleGenerateRequest,
    db: DbSession,
    user_id: CurrentUserId,
):
    result = await generate_puzzle(
        db=db,
        user_id=UUID(user_id),
        template_id=body.template_id,
        item_ids=body.item_ids,
    )
    return success(
        data=PuzzleGenerateResponse.model_validate(result).model_dump(by_alias=True)
    )


@router.get("/results")
async def get_puzzle_results(
    db: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    results, total = await list_puzzle_results(
        db=db, user_id=UUID(user_id), limit=limit, offset=offset
    )
    return success(
        data={
            "list": [
                PuzzleResultOut.model_validate(r).model_dump(by_alias=True)
                for r in results
            ],
            "total": total,
        }
    )


@router.get("/results/{result_id}")
async def get_puzzle_result_detail(
    result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    puzzle_result = await get_puzzle_result(
        db=db, user_id=UUID(user_id), result_id=result_id
    )
    return success(
        data=PuzzleResultOut.model_validate(puzzle_result).model_dump(by_alias=True)
    )


@router.post("/results/{result_id}/share")
async def share_puzzle(
    result_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
    title: Annotated[str | None, Query(max_length=200)] = None,
):
    post = await share_puzzle_result(db=db, user_id=UUID(user_id), puzzle_result_id=result_id, title=title)
    return success(data={"post_id": post.id})
