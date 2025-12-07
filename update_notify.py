import asyncio
from core.database import db

async def update():
    await db.connect()
    async with db.pg_pool.acquire() as conn:
        print("正在更新数据库...")
        # 1. 增加通知开关 (默认开启)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_paused BOOLEAN DEFAULT FALSE")
        # 2. 增加精简模式 (默认关闭)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_simple_mode BOOLEAN DEFAULT FALSE")
        # 3. 增加通知目标 (默认 NULL=发给自己)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_target_id BIGINT DEFAULT NULL")
        # 4. 增加目标名称 (用于显示)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS notify_target_name VARCHAR(255) DEFAULT NULL")
        print("✅ 数据库字段更新完毕")
    await db.close()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except: pass
    asyncio.run(update())