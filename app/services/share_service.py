from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.core.timezone import now_bj
from app.models.post import Post
from app.models.puzzle_result import PuzzleResult
from app.models.tryon_result import TryonResult
from app.models.user import User
from app.services.task_service import complete_task


async def _get_user_info(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundException("用户不存在")
    return user


async def share_tryon_result(
    db: AsyncSession, user_id: UUID, tryon_result_id: UUID, title: str | None = None
) -> Post:
    """将 AI 试穿结果分享到社区。"""
    result = await db.execute(
        select(TryonResult).where(
            TryonResult.id == tryon_result_id,
            TryonResult.user_id == user_id,
        )
    )
    tryon_result = result.scalar_one_or_none()
    if tryon_result is None:
        raise NotFoundException("试穿记录不存在")
    if not tryon_result.result_image_url:
        raise NotFoundException("试穿结果尚未生成")

    user = await _get_user_info(db, user_id)

    post = Post(
        user_id=user_id,
        author_name=user.nickname,
        author_avatar_color=user.avatar_color,
        title=title or "我的 AI 试穿",
        images=[tryon_result.result_image_url],
        style="ai_tryon",
        created_at=now_bj(),
        updated_at=now_bj(),
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    await complete_task(db=db, user_id=user_id, trigger_event="first_share")

    return post


async def share_puzzle_result(
    db: AsyncSession, user_id: UUID, puzzle_result_id: UUID, title: str | None = None
) -> Post:
    """将拼图结果分享到社区。"""
    result = await db.execute(
        select(PuzzleResult).where(
            PuzzleResult.id == puzzle_result_id,
            PuzzleResult.user_id == user_id,
        )
    )
    puzzle_result = result.scalar_one_or_none()
    if puzzle_result is None:
        raise NotFoundException("拼图记录不存在")
    if not puzzle_result.result_image_url:
        raise NotFoundException("拼图结果尚未生成")

    user = await _get_user_info(db, user_id)

    post = Post(
        user_id=user_id,
        author_name=user.nickname,
        author_avatar_color=user.avatar_color,
        title=title or "我的穿搭拼图",
        images=[puzzle_result.result_image_url],
        style="puzzle",
        created_at=now_bj(),
        updated_at=now_bj(),
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)

    await complete_task(db=db, user_id=user_id, trigger_event="first_share")

    return post
