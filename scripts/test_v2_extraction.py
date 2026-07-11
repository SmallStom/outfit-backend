"""小规模测试 V2 属性提取：支持本地 vllm 模型 + 本地图片。

用法：
    # 用本地 vllm 测试 50shop 前2张图片
    python -m scripts.test_v2_extraction --local --count 2

    # 自定义本地模型地址和名称
    python -m scripts.test_v2_extraction --local --model-url http://192.168.1.119:8012 --model-name Qwen3.6-27B --count 2

    # 用 DashScope 远程模型测试（需要 .env 配置）
    python -m scripts.test_v2_extraction --count 2

    # 测试单张本地图片
    python -m scripts.test_v2_extraction --local --image scripts/data/50shop/images/img_6256156.jpg
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import mimetypes
import sys
from pathlib import Path

# Windows 终端 GBK 编码兼容
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

import httpx

# 确保能 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.prompts import ATTRIBUTE_SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_v2_extraction")

# 本地 vllm 默认配置
_DEFAULT_LOCAL_MODEL_URL = "http://192.168.1.119:8012"
_DEFAULT_LOCAL_MODEL_NAME = "Qwen3.6-27B"

# 50shop 数据目录
_SHOP_DATA_DIR = Path(__file__).parent / "data" / "50shop"

# V2 关键字段
_V2_LAYER2_KEYS = ["silhouette", "visual_weight", "volume", "drape", "structure", "visual_focus", "length"]
_V2_LAYER3_KEY = "style_vector"
_V2_LAYER4_KEYS = ["occasion_scores", "season_scores", "pairing_preferences"]


def _image_to_base64_url(image_path: Path) -> str:
    """将本地图片转为 base64 data URL。"""
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if mime_type is None:
        mime_type = "image/jpeg"
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _load_shop_images(count: int) -> list[tuple[str, Path]]:
    """从 items.json 加载测试图片 (name, local_image_path)。"""
    data_path = _SHOP_DATA_DIR / "items.json"
    if not data_path.exists():
        logger.error("items.json not found at %s", data_path)
        return []
    items = json.loads(data_path.read_text(encoding="utf-8"))
    result = []
    for item in items[:count]:
        name = item.get("name", "unknown")[:40]
        local_path = item.get("localImagePath", "")
        if local_path:
            full_path = _SHOP_DATA_DIR / local_path
            if full_path.exists():
                result.append((name, full_path))
            else:
                logger.warning("image not found: %s", full_path)
    return result


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON。"""
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # 代码块 ```json ... ```
    if "```" in text:
        start = text.find("```")
        end = text.rfind("```")
        if start < end:
            block = text[start:end]
            # 去掉 ```json 或 ``` 前缀
            block = block.split("\n", 1)[-1] if "\n" in block else block[3:]
            try:
                return json.loads(block.strip())
            except ValueError:
                pass
    # 正则兜底
    import re
    obj_match = re.search(r"\{[\s\S]*\}", text)
    if obj_match:
        try:
            return json.loads(obj_match.group(0))
        except ValueError:
            pass
    raise ValueError(f"无法提取 JSON: {text[:200]}")


async def _extract_with_local_vllm(
    image_url: str,
    model_url: str,
    model_name: str,
    api_key: str | None = None,
) -> dict:
    """调用本地 vllm 服务器进行 V2 属性提取。"""
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": ATTRIBUTE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": "请分析这张服装图片。"},
                ],
            },
        ],
        "temperature": 0.2,
        "chat_template_kwargs": {"enable_thinking": False},  # vLLM 正确关闭 Qwen3 思考模式
    }
    # vllm 可能需要 response_format，但如果模型不支持 json_object 则去掉
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    url = model_url.rstrip("/") + "/v1/chat/completions"
    logger.info("calling local vllm: %s model=%s", url, model_name)

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        # 如果 response_format 不被支持，去掉重试
        if resp.status_code == 400 and "response_format" in resp.text:
            logger.warning("response_format not supported, retrying without it")
            payload.pop("response_format", None)
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
        else:
            logger.error("vllm error %d: %s", resp.status_code, resp.text[:500])
            raise
    except httpx.HTTPError as exc:
        logger.error("vllm request failed: %s", exc)
        raise

    content = data["choices"][0]["message"]["content"]
    logger.info("raw response length: %d", len(content))
    return _extract_json(content)


async def _extract_with_dashscope(image_url: str) -> dict:
    """调用 DashScope 远程模型进行属性提取。"""
    from app.services.ai.dashscope_client import dashscope_client
    return await dashscope_client.extract_attributes(image_url)


def _print_v2_result(name: str, attrs: dict, source: str = "") -> None:
    """格式化打印 V2 属性提取结果。"""
    print(f"\n{'='*80}")
    print(f"  服装: {name}")
    if source:
        print(f"  来源: {source}")
    print(f"{'='*80}")

    if not attrs.get("is_clothing", False):
        print(f"  ❌ 无效服装: {attrs.get('validation_note', '未知原因')}")
        return

    print(f"  ✅ 有效服装")
    print()

    # Layer1
    print("  [Layer1 客观属性]")
    print(f"    分类: {attrs.get('category')} / {attrs.get('subcategory')}")
    print(f"    颜色: {attrs.get('color_palette')} / {attrs.get('color_hex')}")
    print(f"    材质: {attrs.get('material')} (质感: {attrs.get('material_texture')}, 光泽: {attrs.get('glossiness')}, 厚度: {attrs.get('thickness')})")
    print()

    # Layer2
    print("  [Layer2 视觉属性]")
    for key in _V2_LAYER2_KEYS:
        val = attrs.get(key)
        if val is not None:
            print(f"    {key}: {val}")
    print()

    # Layer3
    print("  [Layer3 风格向量]")
    sv = attrs.get(_V2_LAYER3_KEY)
    if isinstance(sv, dict):
        sorted_sv = sorted(sv.items(), key=lambda x: x[1], reverse=True)
        for k, v in sorted_sv:
            if isinstance(v, (int, float)):
                bar = "█" * int(v * 20)
                print(f"    {k:12s}: {v:.2f} {bar}")
            else:
                print(f"    {k:12s}: {v}")
    else:
        print("    (缺失)")
    print()

    # Layer4
    print("  [Layer4 搭配属性]")
    for key in _V2_LAYER4_KEYS:
        val = attrs.get(key)
        if val is not None:
            print(f"    {key}: {json.dumps(val, ensure_ascii=False)}")
    print(f"    suitable_temperature: {attrs.get('suitable_temperature')}")
    print()

    # 其他
    print("  [其他]")
    print(f"    keywords: {attrs.get('keywords')}")
    desc = attrs.get("visual_description", "")
    print(f"    visual_description: {desc[:120]}{'...' if len(desc) > 120 else ''}")
    print()

    # 缺失字段检查
    missing = []
    for key in _V2_LAYER2_KEYS:
        if attrs.get(key) is None:
            missing.append(key)
    if not isinstance(sv, dict):
        missing.append(_V2_LAYER3_KEY)
    for key in _V2_LAYER4_KEYS:
        if attrs.get(key) is None:
            missing.append(key)
    if missing:
        print(f"  ⚠️  缺失字段: {', '.join(missing)}")
    else:
        print(f"  ✅ 所有 V2 字段均已提取")
    print()


async def _run(
    use_local: bool,
    count: int,
    image_path: str | None,
    model_url: str,
    model_name: str,
    api_key: str | None,
) -> None:
    # 收集测试图片
    test_images: list[tuple[str, str]] = []  # (name, image_url_or_data_url)

    if image_path:
        p = Path(image_path)
        if not p.is_absolute():
            p = Path.cwd() / p
        if not p.exists():
            logger.error("图片不存在: %s", p)
            return
        test_images.append((p.name, _image_to_base64_url(p)))
    else:
        shop_images = _load_shop_images(count)
        if not shop_images:
            logger.error("未找到测试图片")
            return
        for name, img_path in shop_images:
            test_images.append((name, _image_to_base64_url(img_path)))

    logger.info("测试 %d 张图片，模型: %s/%s", len(test_images),
                "本地vllm" if use_local else "DashScope",
                model_name if use_local else "远程")

    for name, image_url in test_images:
        try:
            if use_local:
                attrs = await _extract_with_local_vllm(image_url, model_url, model_name, api_key)
                source = f"本地vllm {model_url}"
            else:
                # DashScope 模式需要远程 URL，不支持 base64
                logger.warning("DashScope 模式需要远程图片 URL，跳过本地图片")
                continue
            _print_v2_result(name, attrs, source)
        except Exception as exc:
            logger.error("提取失败 [%s]: %s", name, exc)
            import traceback
            traceback.print_exc()

    print(f"\n{'='*80}")
    print(f"  测试完成，共 {len(test_images)} 张图片")
    print(f"{'='*80}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 V2 属性提取")
    parser.add_argument("--local", action="store_true", help="使用本地 vllm 模型")
    parser.add_argument("--count", type=int, default=2, help="从 50shop 取多少张图（默认2）")
    parser.add_argument("--image", type=str, default=None, help="单张图片路径")
    parser.add_argument("--model-url", type=str, default=_DEFAULT_LOCAL_MODEL_URL, help="本地 vllm 地址")
    parser.add_argument("--model-name", type=str, default=_DEFAULT_LOCAL_MODEL_NAME, help="模型名称")
    parser.add_argument("--api-key", type=str, default=None, help="API Key（vllm 通常不需要）")
    args = parser.parse_args()

    asyncio.run(_run(
        use_local=args.local,
        count=args.count,
        image_path=args.image,
        model_url=args.model_url,
        model_name=args.model_name,
        api_key=args.api_key,
    ))


if __name__ == "__main__":
    main()
