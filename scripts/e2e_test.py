"""端到端测试：初始化 stom 用户衣橱 + V2 属性提取 + 三种场景推荐。

流程：
1. 创建/重置用户 stom
2. 从 50shop 选取 20 件商品（8 top + 8 bottom + 4 dress）
3. 上传图片到 COS
4. 调用本地 vllm (Qwen3.6-27B) 提取 V2 属性
5. 调用 DashScope 生成视觉 embedding
6. 落库 Item + ItemEmbedding
7. 三种场景推荐：31°C 约会 / 15°C 上班 / 8°C 户外徒步
8. 输出详细结果

用法: python -m scripts.e2e_test
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import sys
import time
from pathlib import Path
from uuid import UUID, uuid4

# Windows 终端编码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# 在导入 app 模块前关闭 debug，避免 SQL echo 拖慢查询
import os
os.environ["DEBUG"] = "false"

import httpx
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import settings
settings.debug = False
from app.core.prompts import ATTRIBUTE_SYSTEM_PROMPT
from app.db.session import AsyncSessionLocal, engine as _engine

# 禁用 SQL echo（engine 在导入时已创建，需要直接修改）
_engine.echo = False

from app.models.item import Item
from app.models.item_embedding import ItemEmbedding
from app.models.outfit import Outfit, OutfitItem
from app.models.outfit_feedback import OutfitFeedback
from app.models.user import User
from app.services.ai.dashscope_client import dashscope_client
from app.services.ai.feature_extraction import _apply_attributes, _is_clothing
from app.services.ai.weather_service import WeatherResult
from app.services.cos import upload_bytes_to_cos
from app.services.reco.engine import recommend_daily

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("e2e_test")

# ==================== 配置 ==================== #

LOCAL_VLLM_URL = "http://192.168.1.119:8012"
LOCAL_VLLM_MODEL = "Qwen3.6-27B"
SHOP_DATA_DIR = Path(__file__).parent / "data" / "50shop"
STOM_OPENID = "stom"

# 选取全部测试商品（不限制数量）
N_TOP = 999
N_BOTTOM = 999
N_DRESS = 999

# VLM 并发数（本地 vllm 可承受的并发量）
VLM_CONCURRENCY = 4
# VLM 超时（秒），并发时可能较慢
VLM_TIMEOUT = 120.0

# 三种测试场景
SCENARIOS = [
    {"name": "夏日约会", "temp": 31.0, "text": "晴", "occasion": "date"},
    {"name": "春秋上班", "temp": 15.0, "text": "多云", "occasion": "office"},
    {"name": "冬天户外徒步", "temp": 8.0, "text": "阴", "occasion": "travel"},
]

# ==================== 工具函数 ==================== #

def _load_test_items() -> list[dict]:
    """从 50shop 数据中选取测试商品。"""
    items = json.loads((SHOP_DATA_DIR / "items.json").read_text(encoding="utf-8"))
    # 只选有本地图片的
    valid = [i for i in items if i.get("localImagePath") and (SHOP_DATA_DIR / i["localImagePath"]).exists()]

    tops = [i for i in valid if i["category"] == "top"][:N_TOP]
    bottoms = [i for i in valid if i["category"] == "bottom"][:N_BOTTOM]
    dresses = [i for i in valid if i["category"] == "dress"][:N_DRESS]

    selected = tops + bottoms + dresses
    logger.info("选取 %d 件商品: %d top + %d bottom + %d dress",
                len(selected), len(tops), len(bottoms), len(dresses))
    return selected


def _image_to_bytes(path: Path) -> tuple[bytes, str, str]:
    """读取本地图片，返回 (data, content_type, ext)。"""
    mime_type, _ = mimetypes.guess_type(str(path))
    if mime_type is None:
        mime_type = "image/jpeg"
    ext = mime_type.split("/")[1]
    if ext == "jpeg":
        ext = "jpg"
    with open(path, "rb") as f:
        return f.read(), mime_type, ext


def _image_to_base64_url(path: Path) -> str:
    """本地图片转 base64 data URL。"""
    data, mime, _ = _image_to_bytes(path)
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（增强容错）。"""
    text = text.strip()
    # 1. 直接解析
    try:
        return json.loads(text)
    except ValueError:
        pass
    # 2. 去除 <think&gt;...</think&gt; 标签（部分模型仍会输出思考内容）
    import re
    text = re.sub(r"<think&gt;[\s\S]*?</think&gt;", "", text).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # 3. 代码块 ```json ... ``` 或 ``` ... ```
    if "```" in text:
        # 找所有 ``` 位置
        blocks = text.split("```")
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            # 去掉可能的 json/python 语言标识
            if block.startswith("json"):
                block = block[4:].strip()
            elif block.startswith("python"):
                block = block[6:].strip()
            try:
                return json.loads(block)
            except ValueError:
                continue
    # 4. 正则提取最大的 JSON 对象
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except ValueError:
            pass
    # 5. 最后尝试：找到第一个 { 和最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(text[first:last+1])
        except ValueError:
            pass
    logger.error("JSON解析失败，原始返回: %s", text[:500])
    raise ValueError(f"无法提取 JSON: {text[:200]}")


# ==================== 核心流程 ==================== #

async def _extract_v2_with_local_vllm(image_base64_url: str) -> dict:
    """调用本地 vllm 提取 V2 属性（关闭思考模式 + 重试）。"""
    payload = {
        "model": LOCAL_VLLM_MODEL,
        "messages": [
            {"role": "system", "content": ATTRIBUTE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_base64_url}},
                    {"type": "text", "text": "请分析这张服装图片。"},
                ],
            },
        ],
        "temperature": 0.2,
        # vLLM 正确关闭 Qwen3 思考模式：必须放在 chat_template_kwargs 内
        "chat_template_kwargs": {"enable_thinking": False},
    }
    headers = {"Content-Type": "application/json"}
    url = LOCAL_VLLM_URL.rstrip("/") + "/v1/chat/completions"

    last_exc = None
    for attempt in range(3):  # 最多重试3次
        try:
            async with httpx.AsyncClient(timeout=VLM_TIMEOUT) as client:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 400 and "response_format" in resp.text:
                    payload.pop("response_format", None)
                    continue
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("VLM返回长度=%d (尝试%d)", len(content), attempt + 1)
                return _extract_json(content)
        except (httpx.ReadTimeout, httpx.ConnectTimeout) as exc:
            last_exc = exc
            logger.warning("VLM超时 (尝试%d/3): %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(5)  # 等待5秒后重试
            continue
        except Exception as exc:
            last_exc = exc
            logger.warning("VLM异常 (尝试%d/3): %s", attempt + 1, exc)
            if attempt < 2:
                await asyncio.sleep(3)
            continue
    raise Exception(f"VLM调用失败(3次重试): {type(last_exc).__name__}: {last_exc}")


async def _process_single_item_safe(
    shop_item: dict, index: int, user_id: UUID, sem: asyncio.Semaphore
) -> Item | None:
    """带并发控制的单件商品处理（独立 DB session）。"""
    async with sem:
        name = shop_item["name"][:40]
        logger.info("[%d] 开始处理: %s (%s)", index, name, shop_item["category"])
        t0 = time.time()
        try:
            async with AsyncSessionLocal() as db:
                # 获取 user
                result = await db.execute(select(User).where(User.id == user_id))
                user = result.scalar_one()
                item = await _process_single_item(db, user, shop_item, index)
                return item
        except Exception as exc:
            logger.error("[%d] 处理异常 %s: %s", index, name, exc)
            return None
        finally:
            elapsed = time.time() - t0
            logger.info("[%d] 完成: %s | %.1fs", index, name, elapsed)


async def _setup_v2_weights():
    """覆盖 V2 权重（.env 中是旧 V1 权重）。"""
    settings.reco_weight_style = 0.25
    settings.reco_weight_color = 0.25
    settings.reco_weight_occasion = 0.15
    settings.reco_weight_weather = 0.10
    settings.reco_weight_bias = 0.10
    # silhouette 用默认 0.15
    logger.info("V2 权重已设置: Style=0.25 Color=0.25 Sil=0.15 Occ=0.15 Wea=0.10 Bias=0.10")


async def _create_or_reset_user(db) -> User:
    """创建或获取 stom 用户（不删除已有数据）。"""
    result = await db.execute(select(User).where(User.openid == STOM_OPENID))
    user = result.scalar_one_or_none()

    if user:
        # 统计已有数据
        item_count = await db.execute(
            select(func.count(Item.id)).where(Item.user_id == user.id, Item.is_deleted.is_(False))
        )
        logger.info("用户 stom 已存在，已有 %d 件衣物，跳过提取直接推荐", item_count.scalar())
        return user
    else:
        user = User(openid=STOM_OPENID, nickname="stom", gender="female", is_new_user=False)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info("已创建用户 stom (id=%s)", user.id)

    return user


async def _process_single_item(db, user: User, shop_item: dict, index: int) -> Item | None:
    """处理单件商品：上传COS → V2提取 → embedding → 落库。"""
    name = shop_item["name"][:40]
    category = shop_item["category"]
    image_path = SHOP_DATA_DIR / shop_item["localImagePath"]

    t0 = time.time()

    # 1. 上传图片到 COS
    try:
        img_data, content_type, ext = _image_to_bytes(image_path)
        cos_url = await upload_bytes_to_cos(img_data, content_type, ext, folder="test_items")
    except Exception as exc:
        logger.error("[%d/%s] COS上传失败 %s: %s", index, name, category, exc)
        return None

    # 2. 创建 Item
    item = Item(
        user_id=user.id,
        name=name,
        category=category,
        sub_category=shop_item.get("subCategory"),
        image_url=cos_url,
        price=shop_item.get("price"),
        brand=shop_item.get("brand"),
        material=shop_item.get("material"),
        season=shop_item.get("season"),
        tags=shop_item.get("tags", []),
        feature_status="processing",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)

    # 3. V2 属性提取（本地 vllm）
    try:
        b64_url = _image_to_base64_url(image_path)
        attrs = await _extract_v2_with_local_vllm(b64_url)
    except Exception as exc:
        logger.error("[%d] V2提取失败 %s: %s", index, name, exc)
        item.feature_status = "failed"
        item.feature_error = str(exc)[:200]
        await db.commit()
        return None

    # 4. 校验是否为有效服装
    is_valid, error_note = _is_clothing(attrs)
    if not is_valid:
        logger.warning("[%d] %s 不是有效服装: %s", index, name, error_note)
        item.feature_status = "failed"
        item.feature_error = error_note
        await db.commit()
        return None

    # 5. 写回 V2 属性
    _apply_attributes(item, attrs)
    item.feature_status = "success"

    # 6. Embedding（DashScope）
    try:
        embedding = await dashscope_client.embed_image(cos_url)
        stmt = (
            pg_insert(ItemEmbedding)
            .values(user_id=user.id, item_id=item.id, embedding=embedding)
            .on_conflict_do_update(
                index_elements=["item_id"],
                set_={"embedding": embedding, "user_id": user.id},
            )
        )
        await db.execute(stmt)
    except Exception as exc:
        logger.warning("[%d] embedding失败 %s: %s（属性已保存，推荐将降级）", index, name, exc)

    await db.commit()
    elapsed = time.time() - t0
    logger.info("[%d] %s | %s | sil=%s vol=%s sv=%s | %.1fs",
                index, name[:25], category,
                item.silhouette, item.volume,
                (item.style_vector or {}).get("minimalist", "-"),
                elapsed)
    return item


async def _run_recommendation(db, user: User, scenario: dict) -> list[Outfit]:
    """运行推荐并返回结果。"""
    weather = WeatherResult(
        temperature=scenario["temp"],
        text=scenario["text"],
        humidity=60,
        city="测试",
    )
    logger.info("推荐场景: %s (%.0f°C %s)", scenario["name"], scenario["temp"], scenario["text"])

    try:
        outfits = await recommend_daily(
            db=db,
            user_id=user.id,
            weather=weather,
            force_refresh=True,
            use_llm_rerank=True,  # 启用 LLM 精排
            occasion=scenario["occasion"],  # 传入目标场景
        )
        return outfits
    except Exception as exc:
        logger.error("推荐失败: %s", exc)
        import traceback
        traceback.print_exc()
        return []


def _print_recommendation_results(outfits: list[Outfit], scenario: dict):
    """打印推荐结果。"""
    print(f"\n{'='*80}")
    print(f"  场景: {scenario['name']} ({scenario['temp']:.0f}°C {scenario['text']})")
    print(f"  推荐数量: {len(outfits)}")
    print(f"{'='*80}")

    for i, outfit in enumerate(outfits, 1):
        items = sorted(outfit.items, key=lambda x: x.sort_order)
        is_standalone = len(items) == 1
        top = items[0].item if items else None
        bottom = items[1].item if len(items) > 1 else None

        label = "套装/连衣裙" if is_standalone else "上装"
        print(f"\n  #{i} {outfit.name}")
        print(f"    得分: {outfit.score:.3f}" if outfit.score else "    得分: N/A")
        print(f"    场合: {outfit.occasion} | 天气: {outfit.weather}")
        if is_standalone:
            print(f"    [一件式]")

        if top:
            sv = top.style_vector or {}
            top_styles = sorted(sv.items(), key=lambda x: x[1], reverse=True)[:3]
            style_str = ", ".join(f"{k}={v:.1f}" for k, v in top_styles)
            print(f"    {label}: {top.name}")
            print(f"          图片: {top.image_url}")
            print(f"          廓形={top.silhouette} 宽松={top.volume} 垂坠={top.drape} | {style_str}")
            print(f"          温度={top.suitable_temp_min}~{top.suitable_temp_max}°C")

        if bottom:
            sv = bottom.style_vector or {}
            bot_styles = sorted(sv.items(), key=lambda x: x[1], reverse=True)[:3]
            style_str = ", ".join(f"{k}={v:.1f}" for k, v in bot_styles)
            print(f"    下装: {bottom.name}")
            print(f"          图片: {bottom.image_url}")
            print(f"          廓形={bottom.silhouette} 宽松={bottom.volume} 垂坠={bottom.drape} | {style_str}")
            print(f"          温度={bottom.suitable_temp_min}~{bottom.suitable_temp_max}°C")

        if top and bottom:
            # 计算搭配分析
            from app.services.reco import scorer
            sil_score = scorer.silhouette_balance(
                top.silhouette, bottom.silhouette,
                top.volume, bottom.volume, top.drape, bottom.drape,
            )
            color_score = scorer.color_harmony(top.color_hex_list, bottom.color_hex_list)
            print(f"    搭配分析: 廓形平衡={sil_score:.2f} 色彩协调={color_score:.2f}")

        if outfit.reason:
            print(f"    推荐理由: {outfit.reason}")

    print()


def _print_wardrobe_summary(items: list[Item]):
    """打印衣橱概要。"""
    print(f"\n{'='*80}")
    print(f"  stom 的衣橱概要")
    print(f"{'='*80}")

    from collections import Counter
    cat_count = Counter(i.category for i in items)
    for k, v in sorted(cat_count.items()):
        print(f"    {k}: {v}件")

    success = [i for i in items if i.feature_status == "success"]
    failed = [i for i in items if i.feature_status == "failed"]
    print(f"    提取成功: {len(success)} / {len(items)}")

    if failed:
        print(f"    提取失败:")
        for i in failed:
            print(f"      - {i.name}: {i.feature_error or 'unknown'}")

    # V2 属性覆盖情况
    has_sv = sum(1 for i in success if i.style_vector)
    has_sil = sum(1 for i in success if i.silhouette)
    has_vol = sum(1 for i in success if i.volume)
    has_occ = sum(1 for i in success if i.occasion_scores)
    print(f"    V2 覆盖: style_vector={has_sv}/{len(success)}, silhouette={has_sil}/{len(success)}, "
          f"volume={has_vol}/{len(success)}, occasion_scores={has_occ}/{len(success)}")

    # 风格分布
    from collections import Counter as C
    style_counter = C()
    for i in success:
        if i.style_vector:
            for k, v in i.style_vector.items():
                if isinstance(v, (int, float)) and v > 0.5:
                    style_counter[k] += 1
    if style_counter:
        print(f"    风格分布 (score>0.5):")
        for k, v in style_counter.most_common(5):
            print(f"      {k}: {v}件")

    print()


# ==================== 主流程 ==================== #

import io
import contextlib

# 结果输出文件
OUTPUT_FILE = Path(__file__).parent / "e2e_test_results.md"


class TeeWriter:
    """同时写入 stdout 和 StringIO buffer。"""
    def __init__(self, *writers):
        self.writers = writers
    def write(self, data):
        for w in self.writers:
            w.write(data)
    def flush(self):
        for w in self.writers:
            try:
                w.flush()
            except Exception:
                pass


async def main():
    logger.info("=" * 60)
    logger.info("端到端测试开始")
    logger.info("=" * 60)

    # 1. 设置 V2 权重
    await _setup_v2_weights()
    settings.debug = False  # 关闭 SQL echo

    # 2. 加载测试商品
    shop_items = _load_test_items()

    # 重定向 stdout 到同时写入 buffer 和 console
    buf = io.StringIO()
    tee = TeeWriter(sys.stdout, buf)
    original_stdout = sys.stdout
    sys.stdout = tee

    async with AsyncSessionLocal() as db:
        # 3. 创建或获取用户（不删除已有数据）
        user = await _create_or_reset_user(db)
        logger.info("用户 stom (id=%s)", user.id)

        # 4. 如果用户已有衣物，跳过提取直接推荐
        existing_count = await db.execute(
            select(func.count(Item.id)).where(
                Item.user_id == user.id, Item.is_deleted.is_(False)
            )
        )
        existing_count = existing_count.scalar()

        if existing_count > 0:
            logger.info("已有 %d 件衣物，跳过提取直接推荐", existing_count)
        else:
            # 并发处理所有商品
            logger.info("开始并发处理 %d 件商品（并发数=%d）...", len(shop_items), VLM_CONCURRENCY)
            sem = asyncio.Semaphore(VLM_CONCURRENCY)
            tasks = [
                _process_single_item_safe(si, idx, user.id, sem)
                for idx, si in enumerate(shop_items, 1)
            ]
            results = await asyncio.gather(*tasks)
            all_items = [r for r in results if r is not None]
            logger.info("商品处理完成，成功 %d/%d 件", len(all_items), len(shop_items))

        # 5. 重新加载所有 item（从不同 session 返回的对象可能已 expired）
        result = await db.execute(
            select(Item).where(Item.user_id == user.id, Item.is_deleted.is_(False))
        )
        all_items = list(result.scalars().all())

        # 6. 打印衣橱概要
        _print_wardrobe_summary(all_items)

        # 7. 三种场景推荐
        for scenario in SCENARIOS:
            outfits = await _run_recommendation(db, user, scenario)
            _print_recommendation_results(outfits, scenario)

    # 恢复 stdout 并写入文件
    sys.stdout = original_stdout
    OUTPUT_FILE.write_text(buf.getvalue(), encoding="utf-8")
    logger.info("=" * 60)
    logger.info("端到端测试完成")
    logger.info("结果已保存到: %s", OUTPUT_FILE)
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
