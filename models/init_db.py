import logging
from core.database import db

logger = logging.getLogger(__name__)

async def init_tables():
    """初始化数据库表结构 (完整版)"""
    if not db.pg_pool: return

    async with db.pg_pool.acquire() as conn:
        try:
            # 1. 用户表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    tg_id BIGINT UNIQUE NOT NULL,
                    username VARCHAR(255),
                    role VARCHAR(20) DEFAULT 'user',
                    balance DECIMAL(10, 2) DEFAULT 0.00,
                    expire_at TIMESTAMP,
                    is_banned BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 2. 关键词表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS keywords (
                    id SERIAL PRIMARY KEY,
                    user_id INT REFERENCES users(id) ON DELETE CASCADE,
                    word VARCHAR(255) NOT NULL,
                    match_mode VARCHAR(20) DEFAULT 'fuzzy',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # 3. 卡密表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS cdks (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(50) UNIQUE NOT NULL,
                    duration INT NOT NULL,
                    unit VARCHAR(10) DEFAULT 'day',
                    status VARCHAR(20) DEFAULT 'unused',
                    used_by INT REFERENCES users(id),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP
                );
            """)

            # 4. 监听账号表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS worker_sessions (
                    id SERIAL PRIMARY KEY,
                    phone VARCHAR(30) UNIQUE,
                    session_string TEXT,
                    status VARCHAR(20) DEFAULT 'offline',
                    last_active TIMESTAMP
                );
            """)

            # 5. 系统设置表 (存广告、支付设置)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS system_settings (
                    key VARCHAR(100) PRIMARY KEY,
                    value TEXT,
                    description VARCHAR(255)
                );
            """)

            # 6. [新增] 机器人菜单配置表 (解决你的问题)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_menus (
                    id SERIAL PRIMARY KEY,
                    row_index INT NOT NULL,
                    text VARCHAR(50) NOT NULL,
                    callback VARCHAR(50) NOT NULL,
                    sort_order INT DEFAULT 0
                );
            """)
            
            # 7. [新增] 预设默认菜单 (防止第一次启动是空的)
            menu_count = await conn.fetchval("SELECT COUNT(*) FROM bot_menus")
            if menu_count == 0:
                await conn.execute("""
                    INSERT INTO bot_menus (row_index, text, callback, sort_order) VALUES
                    (1, '⚙️ 监听管理', 'menu_monitor', 1),
                    (1, '🔔 通知控制', 'menu_notify', 2),
                    (2, '⚠️ 使用说明', 'menu_help', 3),
                    (2, '💎 会员中心', 'menu_profile', 4),
                    (2, '💳 个人中心', 'menu_profile', 5)
                """)

            logger.info("✅ 数据库表结构校验完成")
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            raise e