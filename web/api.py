import os
import secrets
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from core.database import db
from core.config import settings

router = APIRouter(prefix="/api")

# --- Models ---
class LoginRequest(BaseModel):
    phone: str
class VerifyRequest(BaseModel):
    phone: str
    code: str
    password: str = None
class BroadcastRequest(BaseModel):
    user_ids: List[int]
    text: str
class BanRequest(BaseModel):
    user_ids: List[int]
    action: str
class CDKGenRequest(BaseModel):
    type: str; value: int; count: int
class PaymentSettingRequest(BaseModel):
    usdt_address: str; usdt_rate: float; monthly_price: float
class SettingRequest(BaseModel):
    key: str; value: str
class MenuItem(BaseModel):
    row: int; text: str; callback: str
class MenuListRequest(BaseModel):
    items: List[MenuItem]
class AdButton(BaseModel):
    text: str; url: str; sort_order: int
class AdListRequest(BaseModel):
    ads: List[AdButton]
class PresetItem(BaseModel):
    word: str
class PresetListRequest(BaseModel):
    words: List[PresetItem]
class BotCommandItem(BaseModel):
    command: str; description: str
class BotCommandListRequest(BaseModel):
    commands: List[BotCommandItem]
class ReplyMenuItem(BaseModel):
    text: str; row: int; callback: str
class ReplyMenuListRequest(BaseModel):
    items: List[ReplyMenuItem]
class VipPlanItem(BaseModel):
    name: str; price: float; duration: int; unit: str; sort_order: int
class DeletePlanRequest(BaseModel):
    id: int
class DeleteWorkerRequest(BaseModel):
    phone: str

temp_clients = {}

# ===========================
# 1. 支付与套餐管理 (修复重点)
# ===========================

@router.get("/finance/plans")
async def get_vip_plans():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM vip_plans ORDER BY sort_order, id")
            return [dict(r) for r in rows]
    return []

@router.post("/finance/plans")
async def save_vip_plan(data: VipPlanItem):
    """添加套餐"""
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO vip_plans (name, price, duration, unit, sort_order) VALUES ($1, $2, $3, $4, $5)",
                data.name, data.price, data.duration, data.unit, data.sort_order
            )
    return {"status": "success"}

@router.post("/finance/plans/delete")
async def delete_vip_plan(data: DeletePlanRequest):
    """删除套餐"""
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM vip_plans WHERE id = $1", data.id)
    return {"status": "success"}

@router.post("/settings/payment")
async def save_payment_settings(data: PaymentSettingRequest):
    """保存支付设置 (修复版)"""
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            # 逐条更新，确保生效
            await conn.execute("INSERT INTO system_settings (key, value) VALUES ('usdt_address', $1) ON CONFLICT (key) DO UPDATE SET value = $1", data.usdt_address)
            await conn.execute("INSERT INTO system_settings (key, value) VALUES ('usdt_rate', $1) ON CONFLICT (key) DO UPDATE SET value = $1", str(data.usdt_rate))
            # monthly_price 字段如果不需要可以不存，或者保留兼容
    return {"status": "success"}

# ===========================
# 2. 菜单/广告/指令配置
# ===========================
@router.post("/settings/menu")
async def save_bot_menu(data: MenuListRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM bot_menus")
            if data.items:
                values = [(i.row, i.text, i.callback, idx) for idx, i in enumerate(data.items)]
                await conn.executemany("INSERT INTO bot_menus (row_index, text, callback, sort_order) VALUES ($1, $2, $3, $4)", values)
    return {"status": "success"}

@router.get("/settings/menu")
async def get_bot_menu():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM bot_menus ORDER BY row_index, sort_order")
            return [dict(row) for row in rows]
    return []

@router.post("/settings/ads")
async def save_ads_config(data: AdListRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM system_settings WHERE key LIKE 'btn_ad_%'")
            if data.ads:
                values = []
                for i, ad in enumerate(data.ads):
                    key = f"btn_ad_{i}_{ad.text}"
                    values.append((key, ad.url, str(i)))
                await conn.executemany("INSERT INTO system_settings (key, value, description) VALUES ($1, $2, $3)", values)
    return {"status": "success"}

@router.get("/settings/ads")
async def get_ads_config():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value, description FROM system_settings WHERE key LIKE 'btn_ad_%' ORDER BY description::int")
            ads = []
            for r in rows:
                parts = r['key'].split('_', 3)
                text = parts[3] if len(parts) > 3 else "未知"
                ads.append({"text": text, "url": r['value'], "sort_order": int(r['description'])})
            return ads
    return []

@router.post("/settings/presets_list")
async def save_presets_list(data: PresetListRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM keyword_presets")
            if data.words:
                values = [(w.word, i) for i, w in enumerate(data.words)]
                await conn.executemany("INSERT INTO keyword_presets (word, sort_order) VALUES ($1, $2)", values)
    return {"status": "success"}

@router.get("/settings/presets_list")
async def get_presets_list():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM keyword_presets ORDER BY sort_order, id")
            if not rows:
                # 兼容旧逻辑
                old = await conn.fetchval("SELECT value FROM system_settings WHERE key='kw_presets'")
                return [w.strip() for w in old.split(',') if w.strip()] if old else ["监听", "会员"]
            return [r['word'] for r in rows]
    return []

@router.get("/settings/commands")
async def get_bot_commands():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM bot_commands ORDER BY sort_order, id")
            return [dict(r) for r in rows] if rows else [{"command": "menu", "description": "打开菜单"}]
    return []

@router.post("/settings/commands")
async def save_bot_commands(data: BotCommandListRequest):
    from aiogram import Bot
    from aiogram.types import BotCommand, BotCommandScopeDefault
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM bot_commands")
            if data.commands:
                values = [(c.command, c.description, i) for i, c in enumerate(data.commands)]
                await conn.executemany("INSERT INTO bot_commands (command, description, sort_order) VALUES ($1, $2, $3)", values)
    try:
        bot = Bot(token=settings.BOT_TOKEN)
        cmds = [BotCommand(command=c.command, description=c.description) for c in data.commands]
        await bot.set_my_commands(cmds, scope=BotCommandScopeDefault())
        await bot.session.close()
        return {"status": "success"}
    except Exception as e: return {"status": "error", "detail": str(e)}

@router.get("/settings/reply_menus")
async def get_reply_menus():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM reply_menus ORDER BY row_index, sort_order")
            return [dict(r) for r in rows]
    return []

@router.post("/settings/reply_menus")
async def save_reply_menus(data: ReplyMenuListRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM reply_menus")
            if data.items:
                values = [(i.text, i.row, i.callback, idx) for idx, i in enumerate(data.items)]
                await conn.executemany("INSERT INTO reply_menus (text, row_index, callback, sort_order) VALUES ($1, $2, $3, $4)", values)
    return {"status": "success"}

# ===========================
# 3. 其他业务接口
# ===========================
@router.post("/finance/cdks/generate")
async def generate_cdks(data: CDKGenRequest):
    codes = []
    for _ in range(data.count):
        suffix = secrets.token_hex(4).upper()
        unit_str = "D" if data.type == 'day' else "H"
        code = f"VIP-{data.value}{unit_str}-{suffix}"
        codes.append(code)
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.executemany("INSERT INTO cdks (code, duration, unit) VALUES ($1, $2, $3)", [(c, data.value, data.type) for c in codes])
    return {"status": "success", "codes": codes}

@router.get("/finance/cdks")
async def get_recent_cdks():
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            return await conn.fetch("SELECT c.*, u.username as used_by_name FROM cdks c LEFT JOIN users u ON c.used_by = u.id ORDER BY c.id DESC LIMIT 20")
    return []

@router.get("/users/search")
async def search_users(q: Optional[str] = ""):
    if not db.pg_pool: return []
    async with db.pg_pool.acquire() as conn:
        if not q: return await conn.fetch("SELECT * FROM users ORDER BY id DESC LIMIT 50")
        return await conn.fetch("SELECT * FROM users WHERE CAST(tg_id AS TEXT) LIKE $1 OR username ILIKE $1 ORDER BY id DESC LIMIT 50", f"%{q}%")

@router.post("/users/broadcast")
async def broadcast_message(data: BroadcastRequest):
    from aiogram import Bot
    bot = Bot(token=settings.BOT_TOKEN)
    count = 0
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            users = await conn.fetch("SELECT tg_id FROM users WHERE id = ANY($1::int[])", data.user_ids)
            for u in users:
                try: await bot.send_message(chat_id=u['tg_id'], text=data.text); count += 1
                except: pass
    await bot.session.close()
    return {"status": "success", "sent": count}

@router.post("/users/ban")
async def ban_users(data: BanRequest):
    is_banned = True if data.action == 'ban' else False
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("UPDATE users SET is_banned = $1 WHERE id = ANY($2::int[])", is_banned, data.user_ids)
    return {"status": "success"}

@router.post("/settings/trial")
async def save_trial_setting(data: SettingRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("INSERT INTO system_settings (key, value) VALUES ('trial_hours', $1) ON CONFLICT (key) DO UPDATE SET value = $1", data.value)
    return {"status": "success"}

@router.post("/login/send_code")
async def send_code(data: LoginRequest):
    from pyrogram import Client 
    phone = data.phone.replace(" ", "")
    client = Client(name=f"session_{phone}", api_id=os.getenv("API_ID"), api_hash=os.getenv("API_HASH"), in_memory=True)
    try:
        await client.connect()
        sent_code = await client.send_code(phone)
        temp_clients[phone] = {"client": client, "phone_code_hash": sent_code.phone_code_hash}
        return {"status": "success", "message": "验证码已发送"}
    except Exception as e:
        await client.disconnect()
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login/verify")
async def verify_code(data: VerifyRequest):
    from pyrogram.errors import SessionPasswordNeeded
    from pyrogram import Client
    phone = data.phone.replace(" ", "")
    if phone not in temp_clients: raise HTTPException(status_code=400, detail="过期")
    ctx = temp_clients[phone]
    client = ctx["client"]
    try:
        try:
            await client.sign_in(phone, ctx["phone_code_hash"], data.code)
        except SessionPasswordNeeded:
            if not data.password: return {"status": "2fa_required"}
            await client.check_password(data.password)
        session = await client.export_session_string()
        if db.pg_pool:
            async with db.pg_pool.acquire() as conn:
                await conn.execute("INSERT INTO worker_sessions (phone, session_string, status, last_active) VALUES ($1, $2, 'online', NOW()) ON CONFLICT (phone) DO UPDATE SET session_string=$2, status='online'", phone, session)
        await client.disconnect()
        del temp_clients[phone]
        return {"status": "success", "message": "登录成功"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/workers/delete")
async def delete_worker(data: DeleteWorkerRequest):
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM worker_sessions WHERE phone = $1", data.phone)
    return {"status": "success"}