import os
import shutil
import zipfile
import asyncio
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from core.database import db
from core.config import settings
from opentele.td import TDesktop
from opentele.api import API, CreateNewSession
import logging

# 创建独立路由
router = APIRouter(prefix="/api/dm")
logger = logging.getLogger("DM_API")

# --- Models ---
class DMAccount(BaseModel):
    phone: str
    proxy: str = None
    daily_limit: int = 50

class TemplateItem(BaseModel):
    name: str
    content_type: str
    text_content: str
    media_file_id: str = None
    trigger: str = None

# ===========================
# 1. 账号管理 (含 Tdata 解析)
# ===========================

@router.get("/accounts")
async def list_dm_accounts():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM dm_accounts ORDER BY id DESC")
    return []

@router.post("/upload_tdata")
async def upload_tdata_account(file: UploadFile = File(...), proxy: str = Form(None)):
    """
    核心黑科技：接收 Tdata zip -> 解压 -> 转换 Session -> 入库
    """
    temp_dir = f"temp_tdata_{file.filename}"
    os.makedirs(temp_dir, exist_ok=True)
    zip_path = f"{temp_dir}/tdata.zip"
    
    try:
        # 1. 保存上传的 ZIP
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. 解压
        tdata_folder = f"{temp_dir}/tdata"
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(tdata_folder)
            
        # 3. 使用 opentele 转换
        # TDesktop 会自动寻找 key_datas
        tdesk = TDesktop(tdata_folder)
        
        # 检查是否加载成功
        if not tdesk.isLoaded():
            raise Exception("Tdata 文件损坏或格式不正确 (请确保上传的是包含 tdata 文件夹的 zip)")

        # 转换为 Pyrogram Session
        # 使用你自己的 API ID
        api = API.TelegramDesktop(api_id=int(settings.API_ID), api_hash=settings.API_HASH)
        client = await tdesk.ToPyrogramClient(session=CreateNewSession(), api=api)
        
        # 获取信息
        await client.connect()
        me = await client.get_me()
        session_str = await client.export_session_string()
        phone = me.phone_number or f"ID_{me.id}"
        await client.disconnect()
        
        # 4. 入库
        if db.pg_pool:
            async with db.pg_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO dm_accounts (phone, session_string, status, proxy_url)
                    VALUES ($1, $2, 'ready', $3)
                """, str(phone), session_str, proxy)

        return {"status": "success", "message": f"账号 +{phone} 导入成功！"}

    except Exception as e:
        logger.error(f"Tdata Error: {e}")
        return {"status": "error", "detail": f"解析失败: {str(e)}"}
        
    finally:
        # 清理垃圾文件
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.post("/accounts/delete")
async def delete_dm_account(data: dict):
    # data: {"id": 1}
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM dm_accounts WHERE id = $1", data['id'])
    return {"status": "success"}

# ===========================
# 2. 话术模板管理
# ===========================

@router.get("/templates")
async def list_templates():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM dm_templates ORDER BY id DESC")
    return []

@router.post("/templates")
async def save_template(data: TemplateItem):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO dm_templates (name, content_type, text_content, media_file_id, trigger_keywords)
                VALUES ($1, $2, $3, $4, $5)
            """, data.name, data.content_type, data.text_content, data.media_file_id, data.trigger)
    return {"status": "success"}

@router.post("/templates/delete")
async def delete_template(data: dict):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM dm_templates WHERE id = $1", data['id'])
    return {"status": "success"}