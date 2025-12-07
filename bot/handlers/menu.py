from typing import Union
from aiogram import Router, F, types
from aiogram.filters import Command, BaseFilter, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from core.database import db
from bot.keyboards import get_dynamic_menu
from bot.states import ProfileStates
import datetime

# 引入各模块入口
from bot.handlers.monitor import show_monitor_home
from bot.handlers.notify import show_notify_panel
from bot.handlers.personal import show_profile
from bot.handlers.payment import show_vip_plans
from bot.handlers.autodm import show_autodm_panel
from bot.handlers.support import show_support_panel

# 🟢 [修复点] 必须先定义 router，否则后面 @router 都会报错
router = Router()

# ==================================================================
# 0. 自定义过滤器 (精准识别底部按钮)
# ==================================================================
class IsReplyMenu(BaseFilter):
    async def __call__(self, message: types.Message) -> Union[bool, dict]:
        text = message.text
        if not text: return False
        
        # 🟢 双重保险：如果文本像卡密，直接返回 False (不拦截)，让 payment.py 处理
        if text.upper().startswith("VIP-"):
            return False

        callback = None
        if db.pg_pool:
            async with db.pg_pool.acquire() as conn:
                callback = await conn.fetchval("SELECT callback FROM reply_menus WHERE text = $1", text)
        
        if not callback:
            # 兼容性硬编码匹配
            if "购买会员" in text or "会员充值" in text or "💎" in text: callback = "buy_vip"
            elif "个人中心" in text: callback = "menu_profile"
            elif "监听管理" in text: callback = "menu_monitor"
            elif "通知" in text: callback = "menu_notify"
            elif "客服" in text: callback = "menu_support"
            
        if callback: return {"button_callback": callback}
        return False

# ==================================================================
# 1. 辅助函数
# ==================================================================

async def check_user_expired(user_id: int) -> bool:
    if not db.pg_pool: return False
    async with db.pg_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT role, expire_at FROM users WHERE tg_id = $1", user_id)
        if not user: return False 
        now = datetime.datetime.now()
        if user['role'] == 'free': return True
        if user['expire_at'] and user['expire_at'] < now: return True
    return False

async def send_expired_alert(message: types.Message, user_id):
    async with db.pg_pool.acquire() as conn:
        expire_at = await conn.fetchval("SELECT expire_at FROM users WHERE tg_id = $1", user_id)
    time_str = str(expire_at) if expire_at else "未开通"
    text = f"⚠️ <b>服务已到期</b>\n\n您的监听服务已于 {time_str} 到期，\n请及时续费以使用此监听服务！"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 点击购买会员", callback_data="buy_vip")]])
    try:
        await message.answer(text, parse_mode="HTML", reply_markup=kb)
    except: pass

async def get_reply_main_kb():
    if not db.pg_pool: return None
    async with db.pg_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM reply_menus ORDER BY row_index, sort_order")
    if not rows: return None
    keyboard = []; curr_row_idx = -1; curr_row = []
    for row in rows:
        if row['row_index'] != curr_row_idx:
            if curr_row: keyboard.append(curr_row)
            curr_row = []; curr_row_idx = row['row_index']
        curr_row.append(KeyboardButton(text=row['text']))
    if curr_row: keyboard.append(curr_row)
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# ==================================================================
# 2. 基础指令
# ==================================================================

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = message.from_user
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("INSERT INTO users (tg_id, username, role) VALUES ($1, $2, 'free') ON CONFLICT (tg_id) DO UPDATE SET username = $2", user.id, user.username)

    text = (
        f"👋 <b>您好！<a href='tg://user?id={user.id}'>{user.full_name}</a> 欢迎使用荣讯监听！</b>\n\n"
        "我们将为你监听数千个导航索引群中的搜索记录，实时与您设置的关键词作匹配，并将匹配到的用户信息实时推送给您，帮您精准引流。\n\n"
        "👉 点击立即试用：/shiiyon （点击发送 立即试用）\n\n"
        "🎁 <b>我们为每个新用户提供 3 小时的免费试用！</b>\n\n"
        "更多功能设置点击左下角蓝色菜单以及右下角 🎛 按钮"
    )
    # 无论是否过期，都发送底部键盘，方便用户操作
    reply_kb = await get_reply_main_kb()
    await message.answer(text, parse_mode="HTML", reply_markup=reply_kb)

@router.message(Command("shiiyon"))
async def cmd_trial(message: types.Message):
    user_id = message.from_user.id
    async with db.pg_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, has_trialed FROM users WHERE tg_id = $1", user_id)
        if user and user['has_trialed']:
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💎 会员中心", callback_data="buy_vip")]])
            await message.answer("❌ <b>您已经领取过试用福利了！</b>\n请前往会员中心进行充值。", parse_mode="HTML", reply_markup=kb)
            return
        await conn.execute("UPDATE users SET role='trial', expire_at = NOW() + INTERVAL '3 hours', has_trialed = TRUE WHERE tg_id = $1", user_id)
    
    await message.answer(
        "✅ <b>试用开通成功！</b>\n\n"
        "您已获得 3 小时全功能体验。\n"
        "请点击左下角菜单 [/menu] 或下方按钮开始使用。",
        parse_mode="HTML"
    )
    reply_kb = await get_reply_main_kb()
    if reply_kb: await message.answer("👇 快捷菜单已加载", reply_markup=reply_kb)

@router.message(Command("menu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    if await check_user_expired(message.from_user.id):
        await send_expired_alert(message, message.from_user.id)
        return
    reply_kb = await get_reply_main_kb()
    await message.answer(f"👋 <b>欢迎回来，{message.from_user.first_name}</b>", parse_mode="HTML", reply_markup=reply_kb)
    await message.answer("👇 请选择下方功能：", reply_markup=await get_dynamic_menu())

@router.callback_query(F.data == "menu_back")
async def cb_back(callback: types.CallbackQuery):
    if await check_user_expired(callback.from_user.id):
        await send_expired_alert(callback.message, callback.from_user.id)
        return
    await callback.message.edit_text("👋 <b>欢迎回来</b>", parse_mode="HTML", reply_markup=await get_dynamic_menu())

# ==================================================================
# 3. 底部按钮监听 (带过滤器)
# ==================================================================
@router.message(IsReplyMenu(), StateFilter("*")) 
async def handle_bottom_buttons(message: types.Message, state: FSMContext, button_callback: str):
    await state.clear()

    # 3. 检查过期 (白名单：购买会员、联系客服)
    allow_list = ["buy_vip", "menu_support"]
    if button_callback not in allow_list and await check_user_expired(message.from_user.id):
        await send_expired_alert(message, message.from_user.id)
        return

    # 4. 路由
    if button_callback == "menu_monitor": await show_monitor_home(message, state)
    elif button_callback == "menu_notify": await show_notify_panel(message)
    elif button_callback == "menu_profile": await show_profile(message)
    elif button_callback == "buy_vip": await show_vip_plans(message)
    elif button_callback == "menu_autodm": await show_autodm_panel(message)
    elif button_callback == "menu_support": await show_support_panel(message)
    elif button_callback == "menu_back": await cmd_menu(message, state)
    else: await message.answer(f"🚧 功能 [{button_callback}] 开发中...")