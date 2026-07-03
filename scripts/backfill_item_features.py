"""历史存量单品特征回填脚本。

用法：
    python -m scripts.backfill_item_features            # 处理所有 pending/failed 单品
    python -m scripts.backfill_item_features --limit 20 # 最多处理 20 条
    python -m scripts.backfill_item_features --user-id <uuid>
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from uuid import UUID

from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.item import Item
from app.services.ai.feature_extraction import extract_and_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("backfill")


async def _run(limit: int | None, user_id: str | None) -> None:
    async with AsyncSessionLocal() as session:
        stmt = select(Item.id).where(
            Item.is_deleted.is_(False),
            Item.feature_status.in_(["pending", "failed"]),
        )
        if user_id:
            stmt = stmt.where(Item.user_id == UUID(user_id))
        if limit:
            stmt = stmt.limit(limit)
        rows = (await session.execute(stmt)).all()

    ids = [row[0] for row in rows]
    logger.info("total to backfill: %d", len(ids))

    for i, item_id in enumerate(ids, 1):
        async with AsyncSessionLocal() as session:
            logger.info("[%d/%d] processing %s", i, len(ids), item_id)
            try:
                await extract_and_store(session, item_id)
            except Exception:  # noqa: BLE001
                logger.exception("backfill error item=%s", item_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--user-id", type=str, default=None)
    args = parser.parse_args()
    asyncio.run(_run(limit=args.limit, user_id=args.user_id))


if __name__ == "__main__":
    main()
