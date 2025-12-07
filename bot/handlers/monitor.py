import math
from typing import Union
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from bot.states import MonitorStates
from core.database import db

router = Router()
PAGE_SIZE = 10

# ==================================================================
# 1. 监听服务控制中心 (UI 升级版)
# ==================================================================

@router.callback_query(F.data == "menu_monitor")
async def show_monitor_home(event: Union[types.CallbackQuery, types.Message], state: FSMContext = None):
    """显示监听管理主界面 (新版 UI)"""
    if state: await state.clear()
    
    user_id = event.from_user.id
    
    # 初始化变量
    kw_count = 0
    filter_count = 0
    fuzzy_limit = 0
    ai_enabled = False
    role_text = "🆓 免费用户"
    is_vip = False
    target_count = 0

    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", user_id)
            if user:
                uid = user['id']
                kw_count = await conn.fetchval("SELECT COUNT(*) FROM keywords WHERE user_id = $1", uid)
                # 新增统计：过滤词数量
                try:
                    filter_count = await conn.fetchval("SELECT COUNT(*) FROM filter_words WHERE user_id = $1", uid)
                except: pass # 防止表还没建好报错
                
                is_vip = user['role'] == 'vip'
                role_text = "💎 尊享会员" if is_vip else "🆓 免费用户"
                
                # 新增字段读取 (如果没有这些字段会报错，请确保运行了 update_db_v7.py)
                fuzzy_limit = user.get('fuzzy_limit', 0)
                ai_enabled = user.get('ai_filter_enabled', False)

    kw_limit = 80 if is_vip else 5
    limit_text = f"{fuzzy_limit}字" if fuzzy_limit > 0 else "无限制"
    ai_status_text = "已开启" if ai_enabled else "已关闭"
    ai_btn_text = "🧠 关闭 全网最强AI 广告过滤" if ai_enabled else "✅ 开启 全网最强AI 广告过滤"
    
    text = (
        "<b>🤖 监听服务控制中心 🤖</b>\n\n"
        f"🎁 用户身份：<b>{role_text}</b>\n"
        f"🎯 通知开关：✅ 已开启\n"
        f"⚙️ 关键词数量：<b>{kw_count}</b> ({kw_limit} Max)\n"
        f"🛡 过滤词数量：<b>{filter_count}</b> (无限制)\n"
        f"📏 字数限制：<b>{limit_text}</b>\n"
        f"🧠 AI 过滤：<b>{ai_status_text}</b>"
    )

    # 布局：2-2-1-1-2-1 (完全按照你的 UI 截图)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        # Row 1: 关键词 (保留原逻辑入口)
        [InlineKeyboardButton(text="➕ 添加关键词", callback_data="kw_add_start"), InlineKeyboardButton(text="🔍 查看关键词", callback_data="kw_list:1")],
        # Row 2: 过滤词 (新功能)
        [InlineKeyboardButton(text="🚫 添加过滤词", callback_data="filter_add_start"), InlineKeyboardButton(text="🛡 查看过滤词", callback_data="filter_list:1")],
        # Row 3: 字数限制
        [InlineKeyboardButton(text="📏 设置限制模糊关键词字数", callback_data="setting_fuzzy_limit")],
        # Row 4: AI 开关
        [InlineKeyboardButton(text=ai_btn_text, callback_data="setting_toggle_ai")],
        # Row 5: 监听用户 (占位)
        [InlineKeyboardButton(text="➕ 添加监听用户", callback_data="target_add_start"), InlineKeyboardButton(text="📸 监听用户管理", callback_data="target_list")],
        # Row 6: 返回
        [InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")]
    ])

    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# ==================================================================
# 以下全是原有逻辑，完全保留，不做任何修改
# ==================================================================

@router.callback_query(F.data == "kw_add_start")
async def start_add_keyword(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(MonitorStates.waiting_for_keyword)
    
    preset_list = []
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            rows = await conn.fetch("SELECT word FROM keyword_presets ORDER BY sort_order, id")
            preset_list = [r['word'] for r in rows]
    
    if not preset_list: preset_list = ["监听", "会员", "能量"]

    reply_kb_rows = []
    curr = []
    for p in preset_list:
        curr.append(KeyboardButton(text=p))
        if len(curr) == 3:
            reply_kb_rows.append(curr)
            curr = []
    if curr: reply_kb_rows.append(curr)
    reply_kb_rows.append([KeyboardButton(text="❌ 取消")])
    
    reply_markup = ReplyKeyboardMarkup(keyboard=reply_kb_rows, resize_keyboard=True, one_time_keyboard=True)

    text = (
        "[30s] tips：每个关键词通过逗号分隔可以实现批量添加关键词\n"
        "例如：<code>监听, 会员, 能量</code> (点击复制)\n"
        "如需模糊匹配，则可以用 <code>?</code> 替代模糊位置，如：<code>谁?卖?号</code>\n\n"
        "👉 <b>请输入需要监听的关键词：</b>\n"
        "<i>(或点击下方快捷按钮)</i>"
    )
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=reply_markup)
    await callback.answer()

@router.message(MonitorStates.waiting_for_keyword)
async def process_keyword_input(message: types.Message, state: FSMContext):
    if message.text == "❌ 取消":
        await state.clear()
        await message.answer("已取消操作", reply_markup=ReplyKeyboardRemove())
        return

    raw_text = message.text
    keywords = [k.strip() for k in raw_text.replace("，", ",").split(",") if k.strip()]
    
    if not keywords:
        await message.answer("❌ 未识别到有效关键词，请重新输入：")
        return

    user_tg_id = message.from_user.id
    added_count = 0
    fail_reason = ""
    
    async with db.pg_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id, role FROM users WHERE tg_id = $1", user_tg_id)
        current_count = await conn.fetchval("SELECT COUNT(*) FROM keywords WHERE user_id = $1", user['id'])
        limit = 80 if user['role'] == 'vip' else 5
        
        for kw in keywords:
            if current_count >= limit:
                fail_reason = f"⚠️ 达到配额上限 ({limit}个)，请升级会员！"
                break
            exists = await conn.fetchval("SELECT id FROM keywords WHERE user_id = $1 AND word = $2", user['id'], kw)
            if not exists:
                await conn.execute("INSERT INTO keywords (user_id, word) VALUES ($1, $2)", user['id'], kw)
                added_count += 1
                current_count += 1

    msg = f"✅ <b>成功添加了 {added_count} 个关键词</b>"
    if fail_reason: msg += f"\n\n{fail_reason}"
        
    await message.answer(msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    await render_keyword_list(message, user_tg_id, 1)

@router.callback_query(F.data.startswith("kw_list:"))
async def view_keyword_list(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    await render_keyword_list(callback.message, callback.from_user.id, page, is_edit=True)

async def render_keyword_list(message: types.Message, tg_id: int, page: int, is_edit: bool = False):
    async with db.pg_pool.acquire() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE tg_id = $1", tg_id)
        user_db_id = user['id']
        offset = (page - 1) * PAGE_SIZE
        total_count = await conn.fetchval("SELECT COUNT(*) FROM keywords WHERE user_id = $1", user_db_id)
        total_pages = math.ceil(total_count / PAGE_SIZE) if total_count > 0 else 1
        rows = await conn.fetch("SELECT id, word FROM keywords WHERE user_id = $1 ORDER BY id DESC LIMIT $2 OFFSET $3", user_db_id, PAGE_SIZE, offset)

    redis_key = f"sel_kw:{tg_id}"
    selected_ids = set()
    if db.redis:
        selected_ids = await db.redis.smembers(redis_key)

    kb_rows = []
    curr = []
    for row in rows:
        kid = str(row['id'])
        word = row['word']
        is_sel = kid in selected_ids
        btn_text = f"✅ {word}" if is_sel else word
        curr.append(InlineKeyboardButton(text=btn_text, callback_data=f"kw_tog:{kid}:{page}"))
        if len(curr) == 3:
            kb_rows.append(curr)
            curr = []
    if curr: kb_rows.append(curr)

    kb_rows.append([
        InlineKeyboardButton(text="➕ 添加关键词", callback_data="kw_add_start"),
        InlineKeyboardButton(text="🗑 清空关键词", callback_data="kw_clear_all"),
        InlineKeyboardButton(text="🗑 确认删除", callback_data=f"kw_del_confirm:{page}")
    ])

    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"kw_list:{page-1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="🛑 首页", callback_data="none"))
        
    nav_row.append(InlineKeyboardButton(text="❎ 关闭", callback_data="menu_monitor"))
    
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(text="下一页 ➡️", callback_data=f"kw_list:{page+1}"))
    else:
        nav_row.append(InlineKeyboardButton(text="🛑 尾页", callback_data="none"))
    kb_rows.append(nav_row)

    kb_rows.append([
        InlineKeyboardButton(text="💰 开通会员", callback_data="menu_profile"),
        InlineKeyboardButton(text="🔙 返回", callback_data="menu_monitor")
    ])

    text = f"<b>✍️ 关键词列表 ✍️</b>\n\n提示：点击关键词选择，点击删除。\n当前页: {page}/{total_pages} | 总数: {total_count}"
    markup = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    if is_edit:
        await message.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)

@router.callback_query(F.data.startswith("kw_tog:"))
async def toggle_keyword_selection(callback: types.CallbackQuery):
    _, kid, page = callback.data.split(":")
    tg_id = callback.from_user.id
    redis_key = f"sel_kw:{tg_id}"
    if db.redis:
        if await db.redis.sismember(redis_key, kid):
            await db.redis.srem(redis_key, kid)
        else:
            await db.redis.sadd(redis_key, kid)
            await db.redis.expire(redis_key, 300)
    await render_keyword_list(callback.message, tg_id, int(page), is_edit=True)

@router.callback_query(F.data.startswith("kw_del_confirm:"))
async def confirm_delete(callback: types.CallbackQuery):
    page = int(callback.data.split(":")[1])
    tg_id = callback.from_user.id
    redis_key = f"sel_kw:{tg_id}"
    if not db.redis: return
    sids = await db.redis.smembers(redis_key)
    if not sids:
        await callback.answer("⚠️ 请先选择！", show_alert=True)
        return
    ids = [int(i) for i in sids]
    async with db.pg_pool.acquire() as conn:
        await conn.execute("DELETE FROM keywords WHERE id = ANY($1::int[])", ids)
    await db.redis.delete(redis_key)
    await callback.answer(f"已删除 {len(ids)} 个")
    await render_keyword_list(callback.message, tg_id, page, is_edit=True)

@router.callback_query(F.data == "kw_clear_all")
async def clear_all_keywords(callback: types.CallbackQuery):
    tg_id = callback.from_user.id
    async with db.pg_pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", tg_id)
        await conn.execute("DELETE FROM keywords WHERE user_id = $1", uid)
    if db.redis: await db.redis.delete(f"sel_kw:{tg_id}")
    await callback.answer("已清空")
    await render_keyword_list(callback.message, tg_id, 1, is_edit=True)