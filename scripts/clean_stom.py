"""清空 stom 用户的所有数据。"""
import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import text

async def clean():
    async with AsyncSessionLocal() as db:
        uid_sub = "(SELECT id FROM users WHERE openid = 'stom')"
        # 按依赖顺序删除
        stmts = [
            ("outfit_feedbacks", f"WHERE user_id = {uid_sub}"),
            ("outfit_items", f"WHERE outfit_id IN (SELECT id FROM outfits WHERE user_id = {uid_sub})"),
            ("outfits", f"WHERE user_id = {uid_sub}"),
            ("wear_history", f"WHERE user_id = {uid_sub}"),
            ("item_embeddings", f"WHERE user_id = {uid_sub}"),
            ("items", f"WHERE user_id = {uid_sub}"),
        ]
        for table, cond in stmts:
            r = await db.execute(text(f"DELETE FROM {table} {cond}"))
            print(f"{table}: {r.rowcount}")
        r = await db.execute(text(f"DELETE FROM users WHERE openid = 'stom'"))
        print(f"users: {r.rowcount}")
        await db.commit()
        print("Done")

asyncio.run(clean())
