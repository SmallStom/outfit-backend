"""对比云端模型带/不带 chat_template_kwargs 的完整响应。"""
import asyncio
import json
import time
import httpx
from app.core.config import settings

async def test_cloud_vlm():
    image_url = "https://miniprog-1308377146.cos.ap-chengdu.myqcloud.com/test_items/2026-07-08/66a0bb2090024bb0a5ec43a47d1478e9.jpg"

    base_url = settings.ai_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.ai_api_key}",
        "Content-Type": "application/json",
    }

    messages = [
        {"role": "system", "content": "你是服装分析助手。分析图片并返回JSON。"},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": "请分析这张图片的颜色和品类，返回 {\"category\": \"...\", \"color\": \"...\"}"},
            ],
        },
    ]

    # 测试1: 带 chat_template_kwargs
    print("=" * 70)
    print("测试1: 带 chat_template_kwargs={enable_thinking: False}")
    print("=" * 70)
    payload1 = {
        "model": settings.ai_attribute_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload1)
    elapsed1 = time.time() - t0

    print(f"  状态码: {resp.status_code}")
    print(f"  耗时: {elapsed1:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        msg = data["choices"][0]["message"]
        print(f"  message keys: {list(msg.keys())}")
        print(f"  content: {msg.get('content', '')[:500]}")
        if msg.get("reasoning_content"):
            print(f"  reasoning_content (思考内容): {msg['reasoning_content'][:500]}")
        else:
            print(f"  reasoning_content: 无")
        print(f"  finish_reason: {data['choices'][0].get('finish_reason')}")
        print(f"  usage: {data.get('usage', {})}")
    else:
        print(f"  错误: {resp.text[:500]}")

    # 测试2: 不带 chat_template_kwargs
    print()
    print("=" * 70)
    print("测试2: 不带 chat_template_kwargs")
    print("=" * 70)
    payload2 = {
        "model": settings.ai_attribute_model,
        "messages": messages,
        "response_format": {"type": "json_object"},
        "temperature": 0.2,
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{base_url}/chat/completions", headers=headers, json=payload2)
    elapsed2 = time.time() - t0

    print(f"  状态码: {resp.status_code}")
    print(f"  耗时: {elapsed2:.1f}s")
    if resp.status_code == 200:
        data = resp.json()
        msg = data["choices"][0]["message"]
        print(f"  message keys: {list(msg.keys())}")
        print(f"  content: {msg.get('content', '')[:500]}")
        if msg.get("reasoning_content"):
            print(f"  reasoning_content (思考内容): {msg['reasoning_content'][:500]}")
        else:
            print(f"  reasoning_content: 无")
        print(f"  finish_reason: {data['choices'][0].get('finish_reason')}")
        print(f"  usage: {data.get('usage', {})}")
    else:
        print(f"  错误: {resp.text[:500]}")

    print()
    print("=" * 70)
    print(f"对比: 带={elapsed1:.1f}s vs 不带={elapsed2:.1f}s (差值={abs(elapsed1-elapsed2):.1f}s)")

asyncio.run(test_cloud_vlm())
