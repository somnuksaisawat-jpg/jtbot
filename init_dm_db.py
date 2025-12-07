import asyncio
from core.database import db

async def init_dm():
    await db.connect()
    async with db.pg_pool.acquire() as conn:
        print("正在构建私信系统独立数据库...")
        
        # 1. 私信账号表 (DM Matrix)
        # 区别于监听号，这里多了每日限额、代理IP等字段
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_accounts (
                id SERIAL PRIMARY KEY,
                phone VARCHAR(30),
                session_string TEXT NOT NULL,
                status VARCHAR(20) DEFAULT 'ready', -- ready, busy, banned, cooldown
                daily_sent INT DEFAULT 0,
                daily_limit INT DEFAULT 50,
                proxy_url VARCHAR(255),
                last_used_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 2. 话术模板表 (Templates)
        # 支持多媒体 file_id
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_templates (
                id SERIAL PRIMARY KEY,
                name VARCHAR(50),
                content_type VARCHAR(20) DEFAULT 'text', -- text, photo, video
                text_content TEXT,
                media_file_id VARCHAR(255),
                trigger_keywords VARCHAR(255), -- 用于自动回复的触发词
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 3. 任务日志表 (Logs)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS dm_tasks (
                id SERIAL PRIMARY KEY,
                target_user_id BIGINT,
                target_username VARCHAR(255),
                worker_phone VARCHAR(30),
                status VARCHAR(20), -- success, failed
                cost_points INT DEFAULT 0,
                log_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 4. 给用户表增加积分字段 (如果不存在)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS credit INT DEFAULT 0")
        except:
            pass

        print("✅ 私信系统数据库构建完毕！")
    await db.close()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except: pass
    asyncio.run(init_dm())