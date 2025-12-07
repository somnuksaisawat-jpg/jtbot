import asyncio
from core.database import db

async def update():
    await db.connect()
    async with db.pg_pool.acquire() as conn:
        print("正在构建私信系统数据库...")
        
        # 1. 升级用户表 (积分 + 反馈群)
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS credit INT DEFAULT 0")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dm_feedback_chat_id BIGINT DEFAULT NULL")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS dm_feedback_chat_name VARCHAR(255) DEFAULT NULL")
        
        # 2. 私信账号表 (用户级隔离)
        # owner_id: 归属用户
        # daily_limit: 风控限制
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_accounts (
                id SERIAL PRIMARY KEY,
                owner_id INT REFERENCES users(id) ON DELETE CASCADE,
                phone VARCHAR(30),
                session_string TEXT,
                status VARCHAR(20) DEFAULT 'ready', -- ready, busy, banned, cooldown
                daily_sent INT DEFAULT 0,
                daily_limit INT DEFAULT 50,
                proxy_url VARCHAR(255),
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. 私信设置与模板表 (每个用户一条配置)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_settings (
                user_id INT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                is_auto_reply BOOLEAN DEFAULT FALSE,
                reply_content TEXT,
                reply_media_id VARCHAR(255),
                loop_count INT DEFAULT 5, -- 轮询条数
                interval_sec INT DEFAULT 30 -- 发送间隔
            );
        """)
        
        # 4. 私信内容模板表 (主动发送的内容)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_content_templates (
                id SERIAL PRIMARY KEY,
                user_id INT REFERENCES users(id) ON DELETE CASCADE,
                content_type VARCHAR(20) DEFAULT 'text',
                text_content TEXT,
                media_file_id VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        print("✅ 私信数据库构建完毕")
    await db.close()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except: pass
    asyncio.run(update())