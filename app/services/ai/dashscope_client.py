"""DashScope 兼容 OpenAI 接口的多模态 / Embedding / Chat 封装。

统一走 settings.ai_api_key + settings.ai_base_url 配置。
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AIException

logger = logging.getLogger(__name__)

_TIMEOUT = 60.0


# ------------------------------- Attribute extraction ------------------------------- #

ATTRIBUTE_SYSTEM_PROMPT = """你是一位专业服装买手。给定一张服装图片和可选的品类提示，请严格按 JSON Schema 输出：
{
  "category": "上衣|裤子|裙子|外套|鞋履",
  "subcategory": "细分品类，如 T恤/衬衫/卫衣/牛仔裤/半裙/风衣...",
  "color_palette": ["主色", "辅色"],
  "color_hex": ["#RRGGBB", "#RRGGBB"],
  "style_attributes": {
    "formality": 0.0,     // 0 最休闲, 1 最正式
    "femininity": 0.0,    // 0 硬朗, 1 柔美
    "athletic": 0.0,      // 运动感
    "vintage": 0.0        // 复古感
  },
  "material": "文本描述",
  "thickness": 3,         // 1(薄纱) ~ 5(厚呢子)
  "pattern": "纯色|条纹|格纹|印花...",
  "fit": "修身|宽松|直筒|阔腿...",
  "neckline": "圆领|V领|翻领...",
  "length": "短款|常规|中长|长款",
  "suitable_temperature": [minC, maxC],  // 整数摄氏度区间
  "suitable_occasions": ["日常", "通勤", "约会", "运动", "商务", "度假"],
  "keywords": ["温柔", "简约", "百搭"]
}
必须输出合法 JSON，不要包含额外解释文字。数值不要写成字符串。缺失字段用合理默认值填充。"""


RERANK_SYSTEM_PROMPT = """你是一位专业穿搭师。从给定 N 组候选搭配中，选出最协调的 K 组，
并为每组写一句 30 字以内的搭配理由（如：雾霾蓝衬衫与卡其色阔腿裤，冷暖对比，营造知性通勤感）。
输入使用结构化描述（上衣属性、下装属性、当前天气/温度）。
必须返回 JSON 对象：{"picks": [{"index": <候选序号,0起>, "reason": <理由>}]}
picks 数组的长度必须等于 K，不多不少；index 必须落在 [0, N-1] 范围内；不允许重复 index。"""


class _DashScopeClient:
    def __init__(self) -> None:
        self._base_url = settings.ai_base_url.rstrip("/")
        self._api_key = settings.ai_api_key

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            raise AIException("AI_API_KEY 未配置")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # -------------------- 属性提取 -------------------- #
    async def extract_attributes(
        self, image_url: str, category_hint: str | None = None
    ) -> dict[str, Any]:
        if not image_url:
            raise AIException("图片 URL 为空，无法提取属性")

        user_text = "请分析这张服装图片。"
        if category_hint:
            user_text += f" 品类提示：{category_hint}。"

        payload = {
            "model": settings.ai_attribute_model,
            "messages": [
                {"role": "system", "content": ATTRIBUTE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": image_url}},
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("attribute extraction http error: %s", exc)
            raise AIException("属性提取服务不可用") from exc

        try:
            content = data["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("attribute extraction bad response: %s | %s", exc, data)
            raise AIException("属性提取结果解析失败") from exc

    # -------------------- Embedding -------------------- #
    def _is_multimodal_embedding(self) -> bool:
        """多模态/视觉 embedding 模型需走 DashScope 原生接口。"""
        model = settings.ai_embedding_model.lower()
        return "vision" in model or "multimodal" in model

    async def embed_image(self, image_url: str) -> list[float]:
        """调用多模态 embedding，返回向量列表。

        视觉/多模态模型走 DashScope 原生端点；文本模型走 OpenAI 兼容 /embeddings。
        """
        if not image_url:
            raise AIException("图片 URL 为空，无法生成向量")

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                if self._is_multimodal_embedding():
                    # DashScope 原生多模态 embedding 端点
                    url = f"{settings.ai_dashscope_base_url}/services/embeddings/multimodal-embedding/multimodal-embedding"
                    payload = {
                        "model": settings.ai_embedding_model,
                        "input": {"contents": [{"image": image_url}]},
                    }
                    resp = await client.post(
                        url, headers=self._headers(), json=payload
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    vector = data["output"]["embeddings"][0]["embedding"]
                else:
                    # OpenAI 兼容端点
                    payload = {
                        "model": settings.ai_embedding_model,
                        "input": [{"image": image_url}],
                        "encoding_format": "float",
                    }
                    resp = await client.post(
                        f"{self._base_url}/embeddings",
                        headers=self._headers(),
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    vector = data["data"][0]["embedding"]
        except httpx.HTTPError as exc:
            logger.warning("embedding http error: %s", exc)
            raise AIException("向量服务不可用") from exc

        if not isinstance(vector, list) or len(vector) != settings.ai_embedding_dim:
            raise AIException(
                f"embedding 维度异常，期望 {settings.ai_embedding_dim}，实际 {len(vector) if isinstance(vector, list) else 'N/A'}"
            )
        return [float(x) for x in vector]

    # -------------------- Rerank -------------------- #
    async def rerank_outfits(
        self, candidates: list[dict[str, Any]], weather: dict[str, Any], top_n: int
    ) -> list[dict[str, Any]]:
        """输入 Top-K 候选（结构化），输出 top_n 精排结果 + 理由。"""
        if not candidates:
            return []

        user_content = {
            "weather": weather,
            "pick_count": top_n,
            "candidates": candidates,
        }

        payload = {
            "model": settings.ai_rerank_model,
            "messages": [
                {"role": "system", "content": RERANK_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(user_content, ensure_ascii=False),
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.4,
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("rerank http error: %s", exc)
            raise AIException("精排服务不可用") from exc

        try:
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            picks = parsed.get("picks") or []
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            logger.warning("rerank bad response: %s | %s", exc, data)
            raise AIException("精排结果解析失败") from exc

        cleaned: list[dict[str, Any]] = []
        seen: set[int] = set()
        for entry in picks:
            try:
                idx = int(entry.get("index"))
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(candidates) or idx in seen:
                continue
            reason = str(entry.get("reason") or "").strip()
            cleaned.append({"index": idx, "reason": reason[:60]})
            seen.add(idx)
            if len(cleaned) >= top_n:
                break

        return cleaned


dashscope_client = _DashScopeClient()
