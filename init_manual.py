import asyncio
import logging
from core.database import db
from models.init_db import init_tables

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ManualInit")

async def force_init():
    print("🚀 开始手动初始化数据库...")
    
    # 1. 连接数据库
    try:
        await db.connect()
    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        return

    # 2. 执行建表逻辑
    try:
        await init_tables()
        print("✅ 表结构创建成功！(Users, Keywords, CDKs, etc.)")
    except Exception as e:
        print(f"❌ 建表失败: {e}")
    
    # 3. 关闭连接
    await db.close()
    print("✅ 操作结束")

if __name__ == "__main__":
    # 解决 Loop 问题
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except:
        pass
    asyncio.run(force_init())