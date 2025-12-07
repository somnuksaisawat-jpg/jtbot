from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from core.database import db

# 1. 获取 Inline 动态菜单 (原有)
async def get_dynamic_menu():
    """从数据库读取动态菜单"""
    if not db.pg_pool:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚠️ 初始化中...", callback_data="none")]])

    async with db.pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM bot_menus ORDER BY row_index, sort_order")
    
    keyboard = []
    current_row_index = -1
    current_row_buttons = []

    for row in rows:
        btn = InlineKeyboardButton(text=row['text'], callback_data=row['callback'])
        if row['row_index'] != current_row_index:
            if current_row_buttons: keyboard.append(current_row_buttons)
            current_row_buttons = [btn]
            current_row_index = row['row_index']
        else:
            current_row_buttons.append(btn)
            
    if current_row_buttons: keyboard.append(current_row_buttons)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# 2. [新增] 获取 Reply 底部常驻菜单 (从 menu.py 移过来的)
async def get_reply_main_kb():
    """读取底部常驻菜单"""
    if not db.pg_pool: return None
    
    async with db.pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reply_menus ORDER BY row_index, sort_order")
    
    if not rows: return None
    
    keyboard = []
    curr_row_idx = -1
    curr_row = []
    for row in rows:
        if row['row_index'] != curr_row_idx:
            if curr_row: keyboard.append(curr_row)
            curr_row = []
            curr_row_idx = row['row_index']
        curr_row.append(KeyboardButton(text=row['text']))
    if curr_row: keyboard.append(curr_row)
    
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# 3. 监听管理子菜单 (保留)
def monitor_control_kb():
    kb = [
        [InlineKeyboardButton(text="➕ 添加关键词", callback_data="kw_add_start"), InlineKeyboardButton(text="🔍 我的关键词", callback_data="kw_list:1")],
        [InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)