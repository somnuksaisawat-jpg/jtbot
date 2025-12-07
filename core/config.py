import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Web
    WEB_PORT = int(os.getenv("WEB_PORT", 7000))
    
    # Bot
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
    
    # Client (Userbot) - 🟢 关键补全
    API_ID = os.getenv("API_ID")
    API_HASH = os.getenv("API_HASH")
    
    # Postgres
    DB_DSN = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    
    # Redis
    REDIS_URL = f"redis://{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/{os.getenv('REDIS_DB')}"
    if os.getenv("REDIS_PASSWORD"):
        REDIS_URL = f"redis://:{os.getenv('REDIS_PASSWORD')}@{os.getenv('REDIS_HOST')}:{os.getenv('REDIS_PORT')}/{os.getenv('REDIS_DB')}"

settings = Config()