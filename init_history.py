import asyncio
from core.database import db

async def create_table():
    print("正在连接数据库...")
    # 初始化连接池
    await db.connect()
    
    print("正在创建 message_history 表...")
    async with db.pg_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS message_history (
                id SERIAL PRIMARY KEY, 
                user_id BIGINT, 
                chat_id BIGINT, 
                keyword VARCHAR(50), 
                msg_link VARCHAR(255), 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    
    print("✅ 历史记录表创建成功！")
    await db.close()

if __name__ == "__main__":
    asyncio.run(create_table())
