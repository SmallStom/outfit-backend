from uuid import UUID

from fastapi import APIRouter

from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.schemas.body_profile import (
    BodyProfileCreate,
    BodyProfileListResponse,
    BodyProfileOut,
    BodyProfileUpdate,
    BodyType,
    BodyTypeListResponse,
)
from app.services.body_profile_service import (
    BODY_TYPES,
    activate_profile,
    create_profile,
    delete_profile,
    get_profile,
    list_profiles,
    update_profile,
)

router = APIRouter(prefix="/body-profiles", tags=["body-profiles"])


@router.get("/body-types")
async def get_body_types():
    return success(
        data=BodyTypeListResponse(
            list=[BodyType.model_validate(t) for t in BODY_TYPES]
        ).model_dump(by_alias=True)
    )


@router.get("")
async def get_profiles(db: DbSession, user_id: CurrentUserId):
    profiles = await list_profiles(db=db, user_id=UUID(user_id))
    return success(
        data=BodyProfileListResponse(
            list=[BodyProfileOut.model_validate(p) for p in profiles],
            total=len(profiles),
        ).model_dump(by_alias=True)
    )


@router.post("")
async def create_new_profile(
    body: BodyProfileCreate,
    db: DbSession,
    user_id: CurrentUserId,
):
    profile = await create_profile(db=db, user_id=UUID(user_id), data=body)
    return success(
        data=BodyProfileOut.model_validate(profile).model_dump(by_alias=True)
    )


@router.get("/{profile_id}")
async def get_profile_detail(
    profile_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    profile = await get_profile(db=db, user_id=UUID(user_id), profile_id=profile_id)
    return success(
        data=BodyProfileOut.model_validate(profile).model_dump(by_alias=True)
    )


@router.put("/{profile_id}")
async def update_existing_profile(
    profile_id: UUID,
    body: BodyProfileUpdate,
    db: DbSession,
    user_id: CurrentUserId,
):
    profile = await update_profile(
        db=db, user_id=UUID(user_id), profile_id=profile_id, data=body
    )
    return success(
        data=BodyProfileOut.model_validate(profile).model_dump(by_alias=True)
    )


@router.delete("/{profile_id}")
async def remove_profile(
    profile_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    await delete_profile(db=db, user_id=UUID(user_id), profile_id=profile_id)
    return success()


@router.put("/{profile_id}/activate")
async def activate(
    profile_id: UUID,
    db: DbSession,
    user_id: CurrentUserId,
):
    profile = await activate_profile(
        db=db, user_id=UUID(user_id), profile_id=profile_id
    )
    return success(
        data=BodyProfileOut.model_validate(profile).model_dump(by_alias=True)
    )
