from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from bot.states import MonitorStates
from core.database import db
import math

router = Router()
PAGE_SIZE = 10

# 引用 monitor.py 的主界面函数，以便操作完返回
# 注意：这里使用延迟导入或直接构造回调数据返回，避免循环引用
# 我们统一使用 callback="menu_monitor" 返回主菜单

# ===========================
# 1. 字数限制设置
# ===========================
@router.callback_query(F.data == "setting_fuzzy_limit")
async def show_fuzzy_limit_menu(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    current_limit = 0
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            current_limit = await conn.fetchval("SELECT fuzzy_limit FROM users WHERE tg_id = $1", user_id) or 0
    
    status_text = f"{current_limit} 个字内" if current_limit > 0 else "♾️ 不限制"
    
    text = (
        "<b>📏 设置模糊匹配字数限制</b>\n\n"
        f"当前状态：<b>{status_text}</b>\n\n"
        "<b>功能说明：</b>\n"
        "当关键词进行模糊匹配时，如果对方发送的消息长度超过了设定值，系统将自动过滤。\n"
        "<i>场景：防止匹配到长篇大论的垃圾广告文案。</i>"
    )
    
    # 构造选中状态图标
    def limit_btn(val, label):
        icon = "✅ " if current_limit == val else ""
        return InlineKeyboardButton(text=f"{icon}{label}", callback_data=f"set_limit:{val}")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [limit_btn(10, "10个字内"), limit_btn(30, "30个字内")],
        [limit_btn(50, "50个字内"), limit_btn(0, "不限制字数")],
        [InlineKeyboardButton(text="🔙 返回监听管理", callback_data="menu_monitor")]
    ])
    
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("set_limit:"))
async def set_fuzzy_limit(callback: types.CallbackQuery):
    limit = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("UPDATE users SET fuzzy_limit = $1 WHERE tg_id = $2", limit, user_id)
            
    await callback.answer("✅ 设置已更新")
    await show_fuzzy_limit_menu(callback) # 刷新界面显示最新状态

# ===========================
# 2. AI 广告过滤开关
# ===========================
@router.callback_query(F.data == "setting_toggle_ai")
async def toggle_ai_filter(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    new_status = False
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            # 取反
            await conn.execute("UPDATE users SET ai_filter_enabled = NOT ai_filter_enabled WHERE tg_id = $1", user_id)
            new_status = await conn.fetchval("SELECT ai_filter_enabled FROM users WHERE tg_id = $1", user_id)
    
    msg = "✅ 已开启全网最强AI过滤！\n系统将自动拦截高特征值垃圾广告。" if new_status else "🚫 已关闭 AI 过滤。"
    await callback.answer(msg, show_alert=True)
    
    # 返回主菜单刷新状态
    from bot.handlers.monitor import show_monitor_home
    await show_monitor_home(callback)

# ===========================
# 3. 过滤词管理 (添加)
# ===========================
@router.callback_query(F.data == "filter_add_start")
async def start_add_filter(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(MonitorStates.waiting_for_filter_word)
    text = (
        "<b>🚫 添加屏蔽过滤词</b>\n\n"
        "请输入您<b>不想看到</b>的词汇。\n"
        "如果消息中包含这些词，即使命中了关键词，系统也会<b>自动拦截</b>，不进行推送。\n\n"
        "<i>支持批量输入，用逗号分隔。</i>\n"
        "<i>例如：</i> <code>博彩, 兼职, 刷单, 假币</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ 取消", callback_data="menu_monitor")]])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@router.message(MonitorStates.waiting_for_filter_word)
async def process_filter_input(message: types.Message, state: FSMContext):
    text = message.text
    words = [w.strip() for w in text.replace("，", ",").split(",") if w.strip()]
    
    if not words:
        await message.answer("❌ 无效输入，请重新输入或点击取消。")
        return

    count = 0
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            user_id = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", message.from_user.id)
            for w in words:
                exists = await conn.fetchval("SELECT id FROM filter_words WHERE user_id=$1 AND word=$2", user_id, w)
                if not exists:
                    await conn.execute("INSERT INTO filter_words (user_id, word) VALUES ($1, $2)", user_id, w)
                    count += 1
    
    await message.answer(f"✅ 成功添加了 {count} 个过滤词！", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    
    # 跳转到查看列表
    await render_filter_list(message, message.from_user.id, 1, is_edit=False)

# ===========================
# 4. 过滤词管理 (列表查看与删除)
# ===========================
@router.callback_query(F.data.startswith("filter_list:"))
async def view_filter_list(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await render_filter_list(callback.message, callback.from_user.id, page, is_edit=True)

async def render_filter_list(message: types.Message, tg_id: int, page: int, is_edit: bool = False):
    if not db.pg_pool: return
    async with db.pg_pool.acquire() as conn:
        user_id = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", tg_id)
        offset = (page - 1) * PAGE_SIZE
        total = await conn.fetchval("SELECT COUNT(*) FROM filter_words WHERE user_id = $1", user_id)
        total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1
        rows = await conn.fetch("SELECT id, word FROM filter_words WHERE user_id = $1 ORDER BY id DESC LIMIT $2 OFFSET $3", user_id, PAGE_SIZE, offset)

    # 列表按钮
    kb_rows = []
    curr = []
    for r in rows:
        # 点击删除
        curr.append(InlineKeyboardButton(text=f"🗑 {r['word']}", callback_data=f"filter_del:{r['id']}:{page}"))
        if len(curr) == 2: # 每行2个
            kb_rows.append(curr)
            curr = []
    if curr: kb_rows.append(curr)
    
    # 翻页
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"filter_list:{page-1}"))
    if page < total_pages: nav.append(InlineKeyboardButton(text="下一页 ➡️", callback_data=f"filter_list:{page+1}"))
    if nav: kb_rows.append(nav)
    
    kb_rows.append([InlineKeyboardButton(text="➕ 继续添加", callback_data="filter_add_start")])
    kb_rows.append([InlineKeyboardButton(text="🔙 返回监听管理", callback_data="menu_monitor")])
    
    text = f"<b>🛡 过滤词列表 (第 {page}/{total_pages} 页)</b>\n\n点击词汇即可<b>删除</b>。"
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    if is_edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data.startswith("filter_del:"))
async def delete_filter_word(callback: types.CallbackQuery):
    _, fid, page = callback.data.split(":")
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM filter_words WHERE id = $1", int(fid))
    
    await callback.answer("🗑 已删除")
    await render_filter_list(callback.message, callback.from_user.id, int(page), is_edit=True)