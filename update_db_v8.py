import asyncio
import logging
from core.database import db

# 配置日志，确保报错能显示出来
logging.basicConfig(level=logging.INFO)

async def update():
    print("--------------------------------")
    print("🚀 脚本开始运行...")
    
    try:
        print("1. 正在尝试连接数据库...")
        await db.connect()
        print("✅ 数据库连接成功！")
        
        async with db.pg_pool.acquire() as conn:
            print("2. 正在检查/创建黑名单表 (user_blacklist)...")
            # 用户级黑名单表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_blacklist (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    blocked_id BIGINT NOT NULL,
                    blocked_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, blocked_id)
                );
            """)
            print("✅ 表结构升级完毕！")
            
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        print("请检查 .env 配置或数据库状态。")
    finally:
        await db.close()
        print("🛑 脚本运行结束")
        print("--------------------------------")

if __name__ == "__main__":
    try:
        # 兼容性处理
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except:
        pass
    asyncio.run(update())