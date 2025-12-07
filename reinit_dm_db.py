import asyncio
from core.database import db

async def reinit():
    await db.connect()
    async with db.pg_pool.acquire() as conn:
        print("正在重构私信数据库...")
        
        # 1. 私信账号表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_accounts (
                id SERIAL PRIMARY KEY,
                owner_id INT, -- 归属用户ID
                phone VARCHAR(50),
                session_string TEXT,
                status VARCHAR(20) DEFAULT 'ready',
                daily_sent INT DEFAULT 0,
                daily_limit INT DEFAULT 50,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. 私信内容表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_content_templates (
                id SERIAL PRIMARY KEY,
                user_id INT,
                content_type VARCHAR(20) DEFAULT 'text',
                text_content TEXT,
                is_active BOOLEAN DEFAULT TRUE
            );
        """)
        
        # 3. 私信设置表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_settings (
                user_id INT PRIMARY KEY,
                is_auto_reply BOOLEAN DEFAULT FALSE,
                interval_sec INT DEFAULT 30
            );
        """)
        
        # 4. 私信日志表
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_logs (
                id SERIAL PRIMARY KEY,
                user_id INT,
                target_username VARCHAR(100),
                sent_content TEXT,
                status VARCHAR(20),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        print("✅ 私信数据库重构完成")
    await db.close()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except: pass
    asyncio.run(reinit())