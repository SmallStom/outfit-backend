"""Compatibility Model 训练数据准备脚本。

从 Polyvore/IQON 格式的搭配数据或项目自身 outfit_feedbacks 表准备训练集。

用法:
    python -m scripts.compatibility.prepare_data                          # 从 outfit_feedbacks 准备
    python -m scripts.compatibility.prepare_data --polyvore <dir>          # 从 Polyvore 数据集准备
    python -m scripts.compatibility.prepare_data --output data/train.jsonl # 指定输出
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.item_embedding import ItemEmbedding
from app.models.outfit import Outfit, OutfitItem
from app.models.outfit_feedback import OutfitFeedback

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("prepare_data")

# V2 属性特征维度
_STYLE_KEYS = [
    "minimalist", "commute", "street", "sweet", "retro", "sporty",
    "luxury", "y2k", "japanese", "korean", "academic", "gorpcore",
]
_OCCASION_KEYS = ["office", "meeting", "date", "travel", "daily", "party"]
_SEASON_KEYS = ["spring", "summer", "autumn", "winter"]


def extract_feature_vector(item: Item, embedding: list[float] | None) -> list[float]:
    """将 Item 的 V2 属性 + embedding 转为固定长度特征向量。"""
    features: list[float] = []

    # V2 视觉属性 (7维)
    features.append(float(item.silhouette in ("H", "A", "X", "O", "T") and ord(item.silhouette) - 64 if item.silhouette else 0) / 5.0)
    features.append(float(item.visual_weight or 3) / 5.0)
    features.append(float(item.volume or 3) / 5.0)
    features.append(float(item.drape or 3) / 5.0)
    features.append(float(item.structure or 3) / 5.0)
    features.append(float(item.thickness or 3) / 5.0)
    features.append(float(item.suitable_temp_min or 0) / 50.0)

    # style_vector (12维)
    sv = item.style_vector or {}
    for key in _STYLE_KEYS:
        features.append(float(sv.get(key, 0.0)))

    # occasion_scores (6维)
    oc = item.occasion_scores or {}
    for key in _OCCASION_KEYS:
        features.append(float(oc.get(key, 3)) / 5.0)

    # season_scores (4维)
    ss = item.season_scores or {}
    for key in _SEASON_KEYS:
        features.append(float(ss.get(key, 3)) / 5.0)

    # visual embedding (768维，截断或补零)
    if embedding:
        features.extend([float(v) for v in embedding[:768]])
        if len(embedding) < 768:
            features.extend([0.0] * (768 - len(embedding)))
    else:
        features.extend([0.0] * 768)

    return features


async def prepare_from_feedback(output_path: str) -> None:
    """从 outfit_feedbacks 表准备训练数据。"""
    async with AsyncSessionLocal() as db:
        # 查询所有有反馈的 outfit
        stmt = (
            select(OutfitFeedback.outfit_id, OutfitFeedback.action, OutfitFeedback.item_id)
            .where(OutfitFeedback.item_id.is_not(None))
        )
        result = await db.execute(stmt)
        feedbacks = result.all()

        if not feedbacks:
            logger.warning("no feedback data found, generating synthetic data from outfits")
            await prepare_from_outfits(output_path)
            return

        # 按 outfit_id 分组
        outfit_actions: dict[UUID, str] = {}
        for outfit_id, action, _ in feedbacks:
            # like 优先级高于 dislike
            if outfit_id not in outfit_actions or action == "like":
                outfit_actions[outfit_id] = action

        # 查询 outfit items
        positive_pairs: list[tuple[UUID, UUID]] = []
        negative_pairs: list[tuple[UUID, UUID]] = []

        for outfit_id, action in outfit_actions.items():
            stmt = (
                select(OutfitItem.item_id)
                .where(OutfitItem.outfit_id == outfit_id)
                .order_by(OutfitItem.sort_order)
            )
            result = await db.execute(stmt)
            item_ids = [row[0] for row in result.all()]
            if len(item_ids) >= 2:
                pair = (item_ids[0], item_ids[1])
                if action == "like":
                    positive_pairs.append(pair)
                else:
                    negative_pairs.append(pair)

        logger.info("positive pairs: %d, negative pairs: %d", len(positive_pairs), len(negative_pairs))

        # 如果负样本不足，从正样本中随机组合生成
        if len(negative_pairs) < len(positive_pairs):
            all_top_ids = list({p[0] for p in positive_pairs})
            all_bottom_ids = list({p[1] for p in positive_pairs})
            existing = set(positive_pairs) | set(negative_pairs)
            for _ in range(len(positive_pairs) - len(negative_pairs)):
                t = random.choice(all_top_ids)
                b = random.choice(all_bottom_ids)
                if (t, b) not in existing:
                    negative_pairs.append((t, b))
                    existing.add((t, b))

        # 提取特征
        all_item_ids = set()
        for t, b in positive_pairs + negative_pairs:
            all_item_ids.add(t)
            all_item_ids.add(b)

        stmt = select(Item).where(Item.id.in_(list(all_item_ids)))
        items_map = {i.id: i for i in (await db.execute(stmt)).scalars().all()}

        stmt = select(ItemEmbedding.item_id, ItemEmbedding.embedding).where(
            ItemEmbedding.item_id.in_(list(all_item_ids))
        )
        emb_map = {row[0]: list(row[1]) for row in (await db.execute(stmt)).all()}

        # 写入 JSONL
        with open(output_path, "w", encoding="utf-8") as f:
            for top_id, bottom_id in positive_pairs:
                top = items_map.get(top_id)
                bottom = items_map.get(bottom_id)
                if not top or not bottom:
                    continue
                f.write(json.dumps({
                    "top_features": extract_feature_vector(top, emb_map.get(top_id)),
                    "bottom_features": extract_feature_vector(bottom, emb_map.get(bottom_id)),
                    "label": 1,
                }) + "\n")
            for top_id, bottom_id in negative_pairs:
                top = items_map.get(top_id)
                bottom = items_map.get(bottom_id)
                if not top or not bottom:
                    continue
                f.write(json.dumps({
                    "top_features": extract_feature_vector(top, emb_map.get(top_id)),
                    "bottom_features": extract_feature_vector(bottom, emb_map.get(bottom_id)),
                    "label": 0,
                }) + "\n")

        total = len(positive_pairs) + len(negative_pairs)
        logger.info("wrote %d samples to %s", total, output_path)


async def prepare_from_outfits(output_path: str) -> None:
    """从 outfits 表准备数据（所有 AI 生成的搭配视为正样本）。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(OutfitItem.outfit_id, OutfitItem.item_id, OutfitItem.sort_order)
            .join(Outfit, OutfitItem.outfit_id == Outfit.id)
            .where(Outfit.is_ai_generated.is_(True))
        )
        result = await db.execute(stmt)
        rows = result.all()

        # 按 outfit 分组
        outfit_items: dict[UUID, list[UUID]] = {}
        for outfit_id, item_id, sort_order in rows:
            outfit_items.setdefault(outfit_id, []).append(item_id)

        positive_pairs = []
        for outfit_id, item_ids in outfit_items.items():
            if len(item_ids) >= 2:
                positive_pairs.append((item_ids[0], item_ids[1]))

        if not positive_pairs:
            logger.error("no outfit data found for training")
            return

        # 生成负样本
        all_top_ids = list({p[0] for p in positive_pairs})
        all_bottom_ids = list({p[1] for p in positive_pairs})
        existing = set(positive_pairs)
        negative_pairs = []
        for _ in range(len(positive_pairs)):
            t = random.choice(all_top_ids)
            b = random.choice(all_bottom_ids)
            if (t, b) not in existing:
                negative_pairs.append((t, b))
                existing.add((t, b))

        logger.info("positive: %d, negative: %d", len(positive_pairs), len(negative_pairs))

        # 提取特征并写入
        all_item_ids = set()
        for t, b in positive_pairs + negative_pairs:
            all_item_ids.add(t)
            all_item_ids.add(b)

        stmt = select(Item).where(Item.id.in_(list(all_item_ids)))
        items_map = {i.id: i for i in (await db.execute(stmt)).scalars().all()}

        stmt = select(ItemEmbedding.item_id, ItemEmbedding.embedding).where(
            ItemEmbedding.item_id.in_(list(all_item_ids))
        )
        emb_map = {row[0]: list(row[1]) for row in (await db.execute(stmt)).all()}

        with open(output_path, "w", encoding="utf-8") as f:
            for top_id, bottom_id in positive_pairs:
                top = items_map.get(top_id)
                bottom = items_map.get(bottom_id)
                if not top or not bottom:
                    continue
                f.write(json.dumps({
                    "top_features": extract_feature_vector(top, emb_map.get(top_id)),
                    "bottom_features": extract_feature_vector(bottom, emb_map.get(bottom_id)),
                    "label": 1,
                }) + "\n")
            for top_id, bottom_id in negative_pairs:
                top = items_map.get(top_id)
                bottom = items_map.get(bottom_id)
                if not top or not bottom:
                    continue
                f.write(json.dumps({
                    "top_features": extract_feature_vector(top, emb_map.get(top_id)),
                    "bottom_features": extract_feature_vector(bottom, emb_map.get(bottom_id)),
                    "label": 0,
                }) + "\n")

        logger.info("wrote %d samples to %s", len(positive_pairs) + len(negative_pairs), output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="准备 Compatibility Model 训练数据")
    parser.add_argument("--output", type=str, default="data/train.jsonl", help="输出文件路径")
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    asyncio.run(prepare_from_feedback(str(output_path)))


if __name__ == "__main__":
    main()
