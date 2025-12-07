import asyncpg
import logging
from redis import asyncio as aioredis
from core.config import settings

logger = logging.getLogger(__name__)

class DataStore:
    def __init__(self):
        self.pg_pool = None
        self.redis = None

    async def connect(self):
        # 1. 连接 PostgreSQL
        try:
            self.pg_pool = await asyncpg.create_pool(settings.DB_DSN)
            logger.info("✅ PostgreSQL 连接成功")
        except Exception as e:
            logger.error(f"❌ PostgreSQL 连接失败: {e}")
            raise e

        # 2. 连接 Redis
        try:
            self.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            await self.redis.ping()
            logger.info("✅ Redis 连接成功")
        except Exception as e:
            logger.error(f"❌ Redis 连接失败: {e}")
            raise e

    async def close(self):
        if self.pg_pool:
            await self.pg_pool.close()
        if self.redis:
            await self.redis.close()

# 单例模式
db = DataStore()