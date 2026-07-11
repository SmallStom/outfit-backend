"""AI 衣橱顾问 Agent API 路由。"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.rate_limiter import check_rate_limit
from app.core.responses import success
from app.db.dependencies import CurrentUserId, DbSession
from app.services.ai.wardrobe_agent import WardrobeAgent

router = APIRouter(prefix="/wardrobe-agent", tags=["wardrobe-agent"])


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=500, description="用户消息")
    history: list[dict[str, str]] | None = Field(
        default=None, description="历史对话列表"
    )


@router.post("/chat")
async def agent_chat(
    body: AgentChatRequest,
    db: DbSession,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """AI 衣橱顾问对话端点。

    接收用户消息和历史对话，返回 AI 回复。
    """
    check_rate_limit(user_id, "wardrobe-agent:chat", cooldown_seconds=5)

    agent = WardrobeAgent(db=db)
    reply = await agent.chat(
        user_id=UUID(user_id),
        message=body.message,
        history=body.history,
    )
    return success(data={"reply": reply})
