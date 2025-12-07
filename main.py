import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher
from core.config import settings
from core.database import db
from models.init_db import init_tables

# 导入路由
from web.routes import router as web_router
from web.api import router as api_router
from web.dm_api import router as dm_router  # 🟢 必须有这个
from bot.handlers import router as bot_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("Main")

bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
dp.include_router(bot_router)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 系统启动...")
    await db.connect()
    await init_tables()
    asyncio.create_task(dp.start_polling(bot, skip_updates=True))
    logger.info("🤖 机器人监听已启动")
    yield
    print("🛑 系统关闭...")
    await bot.session.close()
    await db.close()

app = FastAPI(title="TG Monitor SaaS", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.include_router(web_router)
app.include_router(api_router)
app.include_router(dm_router) # 🟢 必须注册这个

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.WEB_PORT)