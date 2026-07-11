"""快速测试 PostgreSQL 查询性能。"""
import asyncio
import time
import asyncpg
from app.core.config import settings

async def test():
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    print(f"连接: {dsn}")
    conn = await asyncpg.connect(dsn)
    
    # 1. 简单 count
    t0 = time.time()
    r = await conn.fetchval("SELECT count(*) FROM items")
    print(f"count items: {r} rows in {time.time()-t0:.2f}s")
    
    # 2. count embeddings
    t0 = time.time()
    r = await conn.fetchval("SELECT count(*) FROM item_embeddings")
    print(f"count embeddings: {r} rows in {time.time()-t0:.2f}s")
    
    # 3. 查 1 条 item（不含 JSONB 大字段）
    t0 = time.time()
    r = await conn.fetch("SELECT id, name, category FROM items LIMIT 1")
    print(f"select 1 item (no jsonb): {time.time()-t0:.2f}s")
    
    # 4. 查 1 条 item（全部字段）
    t0 = time.time()
    r = await conn.fetch("SELECT * FROM items LIMIT 1")
    print(f"select 1 item (all cols): {time.time()-t0:.2f}s")
    
    # 5. 查 100 条 item（全部字段）
    t0 = time.time()
    r = await conn.fetch("SELECT * FROM items LIMIT 100")
    print(f"select 100 items (all cols): {time.time()-t0:.2f}s")
    
    # 6. 查 1 条 embedding
    t0 = time.time()
    r = await conn.fetch("SELECT item_id, embedding::text FROM item_embeddings LIMIT 1")
    print(f"select 1 embedding (text): {time.time()-t0:.2f}s")
    
    # 7. 查 10 条 embedding
    t0 = time.time()
    r = await conn.fetch("SELECT item_id, embedding::text FROM item_embeddings LIMIT 10")
    print(f"select 10 embeddings (text): {time.time()-t0:.2f}s")
    
    # 8. 查 274 条 embedding
    t0 = time.time()
    r = await conn.fetch("SELECT item_id, embedding::text FROM item_embeddings LIMIT 274")
    print(f"select 274 embeddings (text): {len(r)} rows in {time.time()-t0:.2f}s")
    
    await conn.close()
    print("Done")

asyncio.run(test())
