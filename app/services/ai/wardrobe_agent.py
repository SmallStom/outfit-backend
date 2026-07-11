"""AI 衣橱顾问 Agent。

基于 DashScope qwen3.7-plus 的 Function Calling，实现自然语言穿搭对话。
支持"今晚见客户穿什么？""明天东京18℃推荐三套""我要显腿长"等自然语言交互。

Agent 主循环：LLM → 工具调用 → 结果整合 → 回复。
"""
from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import Item
from app.services.ai.weather_service import WeatherResult, get_weather
from app.services.outfit_service import recommend_daily
from app.services.reco import shop_recommender
from app.services.reco.wardrobe_gap_analyzer import analyze_wardrobe_gap

logger = logging.getLogger(__name__)

_AGENT_TIMEOUT = 90.0
_MAX_ITERATIONS = 5

# ---------- System Prompt ----------
WARDROBE_AGENT_SYSTEM_PROMPT = """你是「衣橱顾问」，一位专业且亲切的AI时尚造型师。你可以通过工具帮助用户解决穿搭问题。

你的能力：
1. 查询天气信息（get_weather）
2. 推荐穿搭方案（recommend_outfits）—— 基于用户衣橱和外部好物
3. 搜索衣橱中的单品（search_wardrobe）—— 按品类或关键词查找
4. 分析衣橱缺口（analyze_wardrobe_gap）—— 识别缺失品类并推荐补缺商品

对话原则：
- 主动调用合适的工具获取真实信息，不要凭空捏造用户的衣橱内容
- 回复用自然流畅的中文，语气亲切专业
- 穿搭建议要具体可操作，提及颜色搭配、版型建议、场合适配等
- 如果用户提到城市或温度，先调用 get_weather 获取天气再推荐
- 如果用户提到具体场合（如约会、见客户），推荐时注重场合适配
- 如果用户提到身材需求（如显腿长），推荐时注重版型搭配技巧
- 回复控制在200字以内，简洁有力
- 当推荐具体搭配时，说明推荐理由
"""


# ---------- Tools 定义（OpenAI Function Calling 格式） ----------
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询指定城市的当前天气信息，包括温度、天气状况、湿度。用户提到城市名或温度时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如'东京'、'上海'、'北京'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recommend_outfits",
            "description": "基于用户衣橱和外部好物推荐穿搭方案。用户询问'穿什么'、'推荐搭配'、'今日穿搭'时调用。可指定场合、城市、温度。",
            "parameters": {
                "type": "object",
                "properties": {
                    "occasion": {
                        "type": "string",
                        "description": "穿着场合，如'约会'、'通勤'、'见客户'、'日常'、'派对'",
                    },
                    "city": {
                        "type": "string",
                        "description": "城市名称，用于获取天气",
                    },
                    "temperature": {
                        "type": "number",
                        "description": "用户指定的温度（摄氏度），未指定则不传",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wardrobe",
            "description": "搜索用户衣橱中的单品。用户想查找特定品类或关键词的衣物时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "品类筛选，如'top'(上衣)、'bottom'(下装)、'dress'(裙装)、'outerwear'(外套)、'shoes'(鞋履)、'accessory'(配饰)",
                    },
                    "keyword": {
                        "type": "string",
                        "description": "关键词搜索，如'黑色'、'衬衫'、'高腰'",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_wardrobe_gap",
            "description": "分析用户衣橱的品类和颜色缺口，识别缺失项并推荐补缺商品。用户询问'衣橱缺什么'、'需要买什么'、'衣橱分析'时调用。无需参数。",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


class WardrobeAgent:
    """AI 衣橱顾问 Agent。

    通过 Function Calling 实现自然语言穿搭对话。
    每个工具函数实际查询数据库并返回结果。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def chat(
        self,
        user_id: UUID,
        message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Agent 对话主入口。

        Args:
            user_id: 用户 ID
            message: 用户消息
            history: 历史对话 [{"role": "user"|"assistant", "content": "..."}]

        Returns:
            AI 回复文本
        """
        if not settings.ai_api_key:
            return (
                "AI 服务未配置，暂时无法提供对话服务。"
                "请管理员配置 AI_API_KEY 后重试。"
            )

        # 构建消息列表
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": WARDROBE_AGENT_SYSTEM_PROMPT},
        ]

        # 加入历史对话（最多保留最近 10 轮）
        if history:
            for msg in history[-20:]:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        # Agent 主循环
        for _ in range(_MAX_ITERATIONS):
            assistant_message, tool_calls = await self._call_llm(messages)

            if not tool_calls:
                # 没有工具调用，返回最终回复
                return assistant_message or "我暂时无法回答这个问题，请换个方式描述。"

            # 将 assistant 消息（含 tool_calls）加入消息列表
            messages.append({
                "role": "assistant",
                "content": assistant_message,
                "tool_calls": tool_calls,
            })

            # 执行每个工具调用
            for tool_call in tool_calls:
                tool_name = tool_call["function"]["name"]
                try:
                    tool_args = json.loads(tool_call["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    tool_args = {}

                tool_result = await self._execute_tool(
                    tool_name, tool_args, user_id
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_result,
                })

        # 超过最大迭代次数，返回兜底回复
        return "我正在处理你的请求，但信息较多。请尝试更具体地描述你的需求。"

    # ---------- LLM 调用 ----------

    async def _call_llm(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]] | None]:
        """调用 LLM，返回 (content, tool_calls)。"""
        payload: dict[str, Any] = {
            "model": settings.ai_rerank_model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.7,
        }

        try:
            async with httpx.AsyncClient(timeout=_AGENT_TIMEOUT) as client:
                resp = await client.post(
                    f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.ai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("[wardrobe_agent] LLM call failed: %s", exc)
            return "AI 服务暂时不可用，请稍后重试。", None

        try:
            msg = data["choices"][0]["message"]
            content = msg.get("content")
            tool_calls = msg.get("tool_calls")
            return content, tool_calls
        except (KeyError, IndexError, TypeError) as exc:
            logger.warning("[wardrobe_agent] bad LLM response: %s | %s", exc, data)
            return "AI 返回异常，请重试。", None

    # ---------- 工具执行 ----------

    async def _execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        user_id: UUID,
    ) -> str:
        """执行工具调用，返回 JSON 字符串结果。"""
        try:
            if tool_name == "get_weather":
                return await self._tool_get_weather(tool_args)
            elif tool_name == "recommend_outfits":
                return await self._tool_recommend_outfits(tool_args, user_id)
            elif tool_name == "search_wardrobe":
                return await self._tool_search_wardrobe(tool_args, user_id)
            elif tool_name == "analyze_wardrobe_gap":
                return await self._tool_analyze_wardrobe_gap(user_id)
            else:
                return json.dumps(
                    {"error": f"未知工具: {tool_name}"}, ensure_ascii=False
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[wardrobe_agent] tool %s failed: %s", tool_name, exc
            )
            return json.dumps(
                {"error": f"工具执行失败: {exc}"}, ensure_ascii=False
            )

    async def _tool_get_weather(self, args: dict[str, Any]) -> str:
        """查询天气。"""
        city = args.get("city")
        weather = await get_weather(city=city)
        return json.dumps(
            {
                "temperature": weather.temperature,
                "text": weather.text,
                "humidity": weather.humidity,
                "city": weather.city,
            },
            ensure_ascii=False,
        )

    async def _tool_recommend_outfits(
        self, args: dict[str, Any], user_id: UUID
    ) -> str:
        """推荐穿搭方案。"""
        occasion = args.get("occasion")
        city = args.get("city")
        temperature = args.get("temperature")

        # 获取天气
        if temperature is not None:
            weather = WeatherResult(
                temperature=float(temperature),
                text="用户指定",
                city=city or "未知",
            )
        else:
            weather = await get_weather(city=city)

        # 从用户衣橱推荐
        wardrobe_outfits = await recommend_daily(
            db=self.db,
            user_id=user_id,
            weather=weather,
            force_refresh=True,
        )

        # 外部好物推荐
        try:
            shop_combos = await shop_recommender.recommend_shop_outfits(
                db=self.db,
                user_id=user_id,
                weather=weather,
            )
        except Exception:  # noqa: BLE001
            shop_combos = []

        # 格式化衣橱搭配
        wardrobe_list = []
        for outfit in wardrobe_outfits[:3]:
            items_info = []
            for oi in outfit.items:
                items_info.append({
                    "name": oi.item.name,
                    "category": oi.item.category,
                    "color": oi.item.color,
                })
            wardrobe_list.append({
                "name": outfit.name,
                "occasion": outfit.occasion,
                "weather": outfit.weather,
                "reason": outfit.reason,
                "items": items_info,
            })

        # 格式化外部好物
        shop_list = []
        for combo in shop_combos[:2]:
            items_info = []
            for item in combo.get("items", []):
                items_info.append({
                    "name": item.name,
                    "category": item.category,
                    "price": item.price,
                    "source_url": item.source_url,
                })
            shop_list.append({
                "name": combo.get("name"),
                "reason": combo.get("reason"),
                "items": items_info,
            })

        return json.dumps(
            {
                "weather": {
                    "temperature": weather.temperature,
                    "text": weather.text,
                    "city": weather.city,
                },
                "occasion": occasion or "日常",
                "wardrobe_outfits": wardrobe_list,
                "shop_recommendations": shop_list,
                "wardrobe_count": len(wardrobe_list),
                "shop_count": len(shop_list),
            },
            ensure_ascii=False,
            default=str,
        )

    async def _tool_search_wardrobe(
        self, args: dict[str, Any], user_id: UUID
    ) -> str:
        """搜索用户衣橱单品。"""
        category = args.get("category")
        keyword = args.get("keyword")

        stmt = select(Item).where(
            Item.user_id == user_id,
            Item.is_deleted.is_(False),
        )
        if category:
            stmt = stmt.where(Item.category == category)

        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        # 关键词过滤
        if keyword:
            kw = keyword.lower()
            items = [
                item for item in items
                if kw in (item.name or "").lower()
                or kw in (item.sub_category or "").lower()
                or kw in (item.color or "").lower()
                or kw in (item.material or "").lower()
                or any(kw in (t or "").lower() for t in (item.tags or []))
            ]

        # 限制返回数量
        items = items[:10]

        item_list = []
        for item in items:
            item_list.append({
                "name": item.name,
                "category": item.category,
                "sub_category": item.sub_category,
                "color": item.color,
                "material": item.material,
                "occasion": item.occasion,
                "wear_count": item.wear_count,
            })

        return json.dumps(
            {
                "total": len(item_list),
                "items": item_list,
                "query_category": category,
                "query_keyword": keyword,
            },
            ensure_ascii=False,
            default=str,
        )

    async def _tool_analyze_wardrobe_gap(self, user_id: UUID) -> str:
        """分析衣橱缺口。"""
        gaps = await analyze_wardrobe_gap(db=self.db, user_id=user_id)
        return json.dumps(
            {"gaps": gaps},
            ensure_ascii=False,
            default=str,
        )
