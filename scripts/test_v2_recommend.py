"""测试 V2 推荐算法：六维评分 + 避免重复 + 偏好融合。

用法:
    python -m scripts.test_v2_recommend --user <user_id>   # 测试指定用户
    python -m scripts.test_v2_recommend                     # 测试所有有数据的用户
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from uuid import UUID

# 确保能 import app 包
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.core.timezone import now_bj
from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.models.outfit import Outfit, OutfitItem
from app.models.outfit_feedback import OutfitFeedback
from app.models.user import User
from app.services.ai.weather_service import WeatherResult
from app.services.reco import scorer
from app.services.reco.engine import (
    _is_avoided_pair,
    _load_candidates,
    _load_disliked_items,
    _load_feedback_map,
    _load_recent_recommended_items,
    _load_recent_worn_items,
    _score_combo,
    _weights,
)
from app.services.reco.preference_learner import (
    build_preference_profile,
    preference_score,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("test_v2_recommend")


async def _test_user(user_id: UUID) -> None:
    """对指定用户运行 V2 推荐算法测试。"""
    async with AsyncSessionLocal() as db:
        # 1. 加载候选
        weather = WeatherResult(temperature=25.0, text="晴", humidity=60, city="测试")
        try:
            tops, bottoms, emb_map = await _load_candidates(
                db, user_id, weather.temperature, weather.text
            )
        except Exception as exc:
            print(f"\n❌ 候选加载失败: {exc}")
            return

        print(f"\n{'='*80}")
        print(f"  用户: {user_id}")
        print(f"  上装候选: {len(tops)} 件")
        print(f"  下装候选: {len(bottoms)} 件")
        print(f"{'='*80}")

        if not tops or not bottoms:
            print("  候选不足，跳过")
            return

        # 2. 加载 V2 数据
        feedback_map = await _load_feedback_map(db, user_id)
        disliked = await _load_disliked_items(db, user_id)
        recent_worn = await _load_recent_worn_items(db, user_id)
        recent_recommended = await _load_recent_recommended_items(db, user_id)
        pref_profile = await build_preference_profile(db, user_id)

        print(f"\n  [V2 数据加载]")
        print(f"    反馈记录: {len(feedback_map)} 个单品")
        print(f"    软屏蔽单品: {len(disliked)} 个")
        print(f"    近期穿过: {len(recent_worn)} 个")
        print(f"    近期推荐过: {len(recent_recommended)} 个")
        print(f"    偏好画像: {'有' if not pref_profile.is_empty else '无'}")
        if not pref_profile.is_empty:
            print(f"      偏好颜色: {pref_profile.favorite_colors[:3]}")
            print(f"      偏好风格: {pref_profile.favorite_styles[:3]}")
            print(f"      偏好廓形: {pref_profile.favorite_silhouettes[:3]}")

        # 3. 六维评分
        weights = _weights(is_new_user=not feedback_map)
        print(f"\n  [评分权重]")
        for k, v in weights.items():
            print(f"    {k}: {v:.2f}")

        combos = []
        for top in tops:
            for bottom in bottoms:
                if _is_avoided_pair(top, bottom):
                    continue
                scores = _score_combo(
                    top, bottom, emb_map, weather.temperature, feedback_map,
                    disliked, recent_worn, recent_recommended,
                )
                outfit_score = scorer.total_score(scores, weights) - scores.get("penalty", 0.0)
                pref = preference_score(pref_profile, top, bottom) if not pref_profile.is_empty else 0.5
                final = 0.75 * max(0.0, outfit_score) + 0.25 * pref
                combos.append((top, bottom, scores, final, pref))

        # 4. 排序并展示 Top5
        combos.sort(key=lambda x: x[3], reverse=True)
        top5 = combos[:5]

        print(f"\n  [Top5 搭配评分]")
        for i, (top, bottom, scores, final, pref) in enumerate(top5, 1):
            print(f"\n  #{i} {top.name} + {bottom.name}")
            print(f"    最终得分: {final:.3f} (偏好分: {pref:.3f})")
            print(f"    六维明细:")
            for dim in ["style", "color", "silhouette", "occasion", "weather", "bias"]:
                val = scores.get(dim, 0)
                bar = "█" * int(val * 20)
                print(f"      {dim:12s}: {val:.3f} {bar}")
            if scores.get("penalty", 0) > 0:
                print(f"      penalty     : -{scores['penalty']:.3f}")

            # V2 属性展示
            if top.silhouette or top.volume:
                print(f"    上装 V2: silhouette={top.silhouette}, volume={top.volume}, drape={top.drape}")
            if bottom.silhouette or bottom.volume:
                print(f"    下装 V2: silhouette={bottom.silhouette}, volume={bottom.volume}, drape={bottom.drape}")
            if top.style_vector:
                top_styles = sorted(top.style_vector.items(), key=lambda x: x[1], reverse=True)[:3]
                print(f"    上装风格: {', '.join(f'{k}={v:.1f}' for k, v in top_styles)}")

        # 5. 回归检查
        print(f"\n  [回归检查]")
        v2_count = sum(1 for t, b, _, _, _ in combos if t.style_vector and b.style_vector)
        print(f"    有 style_vector 的组合: {v2_count}/{len(combos)}")
        v2_sil = sum(1 for t, b, _, _, _ in combos if t.volume and b.volume)
        print(f"    有 volume 的组合: {v2_sil}/{len(combos)}")
        v2_occ = sum(1 for t, b, _, _, _ in combos if t.occasion_scores and b.occasion_scores)
        print(f"    有 occasion_scores 的组合: {v2_occ}/{len(combos)}")

        print(f"\n{'='*80}\n")


async def _run(user_id: str | None) -> None:
    if user_id:
        await _test_user(UUID(user_id))
        return

    # 找有最多单品的用户
    async with AsyncSessionLocal() as db:
        from sqlalchemy import func
        stmt = (
            select(Item.user_id, func.count().label("cnt"))
            .where(Item.is_deleted.is_(False))
            .group_by(Item.user_id)
            .order_by(func.count().desc())
            .limit(3)
        )
        result = await db.execute(stmt)
        users = result.all()

    if not users:
        print("没有找到有单品的用户")
        return

    for uid, cnt in users:
        print(f"\n发现用户 {uid} 有 {cnt} 件单品")
        await _test_user(uid)


def main() -> None:
    parser = argparse.ArgumentParser(description="测试 V2 推荐算法")
    parser.add_argument("--user", type=str, default=None, help="用户ID")
    args = parser.parse_args()
    asyncio.run(_run(args.user))


if __name__ == "__main__":
    main()
