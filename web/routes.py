from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from core.database import db

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

@router.get("/")
async def dashboard(request: Request):
    """仪表盘：读取真实数据库统计"""
    stats = {
        "users": 0,
        "revenue": "0.00",
        "bots_online": 0,
        "bots_total": 0,
        "msgs_today": 0
    }
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            stats["users"] = await conn.fetchval("SELECT COUNT(*) FROM users")
            stats["bots_total"] = await conn.fetchval("SELECT COUNT(*) FROM worker_sessions")
            stats["bots_online"] = await conn.fetchval("SELECT COUNT(*) FROM worker_sessions WHERE status = 'online'")
            stats["msgs_today"] = 0 # 暂未统计
            
    return templates.TemplateResponse("dashboard.html", {"request": request, "page": "dashboard", "stats": stats})

@router.get("/users")
async def page_users(request: Request):
    """用户管理"""
    users = []
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            users = await conn.fetch("SELECT * FROM users ORDER BY id DESC LIMIT 50")
    
    return templates.TemplateResponse("users.html", {"request": request, "page": "users", "users": users})

@router.get("/finance")
async def page_finance(request: Request):
    """财务页"""
    config = {"usdt_address": ""}
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            config['usdt_address'] = await conn.fetchval("SELECT value FROM system_settings WHERE key='usdt_address'") or ""
            
    return templates.TemplateResponse("finance.html", {"request": request, "page": "finance", "config": config})

@router.get("/monitor")
async def page_monitor(request: Request):
    """广告与菜单"""
    return templates.TemplateResponse("monitor.html", {
        "request": request, 
        "page": "monitor", 
        "ads": [] 
    })

@router.get("/accounts")
async def page_accounts(request: Request):
    """账号池"""
    workers = []
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            workers = await conn.fetch("SELECT * FROM worker_sessions ORDER BY id DESC")
            
    return templates.TemplateResponse("accounts.html", {"request": request, "page": "accounts", "workers": workers})

# 🟢 [关键修复] 补上这个路由，网页才能打开
@router.get("/autodm")
async def page_autodm(request: Request):
    """智能私信矩阵"""
    return templates.TemplateResponse("autodm.html", {"request": request, "page": "autodm"})