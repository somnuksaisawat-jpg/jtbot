import math
from typing import Union
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from aiogram.types.keyboard_button_request_chat import KeyboardButtonRequestChat
from core.database import db

router = Router()
PAGE_SIZE = 5

# ==================================================================
# 1. 通知控制面板
# ==================================================================

@router.callback_query(F.data == "menu_notify")
async def show_notify_panel(event: Union[types.CallbackQuery, types.Message]):
    user_id = event.from_user.id
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", user_id)
    
    if not user: 
        text = "请先发送 /start 注册"
        if isinstance(event, types.CallbackQuery): await event.answer(text)
        else: await event.answer(text)
        return

    is_paused = user['is_paused']
    is_simple = user['notify_simple_mode']
    target_name = user['notify_target_name']
    target_id = user['notify_target_id']
    is_vip = user['role'] == 'vip'
    
    status_icon = "⏸ 已暂停" if is_paused else "✅ 已开启"
    mode_icon = "🔕 精简模式" if is_simple else "🔔 普通模式"
    
    if target_id:
        # 这里面板显示的逻辑也需要优化，防止坏链
        # 简单起见，面板只显示名字，点击跳转逻辑放在“更改目标”里更安全
        # 或者我们尝试生成通用链接
        clean_id = str(target_id).replace("-100", "")
        # 尝试生成链接，如果生成不了就只显示名字
        if str(target_id).startswith("-100"):
            target_display = f"📢 <a href='https://t.me/c/{clean_id}/1'>{target_name}</a>"
        else:
            target_display = f"📢 {target_name}"
            
        target_btn_text = "📂 切换通知群组"
    else:
        target_display = "🤖 此对话窗口 (私聊)"
        target_btn_text = "🎯 更改通知目标"
    
    adv_text = ""
    if not is_vip:
        adv_text = "\n------------------\n&lt;ADV&gt; 高级功能仅限 <b>付费会员</b> 可用"

    text = (
        "<b>🔔 通知控制中心 🔔</b>\n"
        "------------------\n"
        f"🎯 监听通知：<b>{status_icon}</b>\n"
        f"📢 通知目标：<b>{target_display}</b>\n"
        f"🔊 通知模式：<b>{mode_icon}</b>"
        f"{adv_text}"
    )
    
    pause_btn_text = "▶️ 恢复通知" if is_paused else "⏸ 暂停通知"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=pause_btn_text, callback_data="notify_toggle_pause"),
            InlineKeyboardButton(text=target_btn_text, callback_data="notify_change_target")
        ],
        [
            InlineKeyboardButton(text="🚫 黑名单管理", callback_data="blacklist_view:1"),
            InlineKeyboardButton(text="🔕 精简/去广告", callback_data="notify_toggle_simple")
        ],
        [
            InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")
        ]
    ])
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

# ... (toggle_pause, check_vip, toggle_simple 保持不变) ...
# 为节省篇幅，这里略去中间未修改的函数，请保留你原文件里的 toggle_pause, check_vip, toggle_simple

@router.callback_query(F.data == "notify_toggle_pause")
async def toggle_pause(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async with db.pg_pool.acquire() as conn:
        await conn.execute("UPDATE users SET is_paused = NOT is_paused WHERE tg_id = $1", user_id)
    await show_notify_panel(callback)

async def check_vip(callback: types.CallbackQuery) -> bool:
    user_id = callback.from_user.id
    async with db.pg_pool.acquire() as conn:
        role = await conn.fetchval("SELECT role FROM users WHERE tg_id = $1", user_id)
    if role != 'vip':
        await callback.answer("🚫 访问受限\n😉 此功能需要 🎖 尊享会员身份", show_alert=True)
        return False
    return True

@router.callback_query(F.data == "notify_toggle_simple")
async def toggle_simple(callback: types.CallbackQuery):
    if not await check_vip(callback): return
    async with db.pg_pool.acquire() as conn:
        await conn.execute("UPDATE users SET notify_simple_mode = NOT notify_simple_mode WHERE tg_id = $1", callback.from_user.id)
    await show_notify_panel(callback)

# ==================================================================
# 3. 更改目标 - 向导 (🟢 修复链接生成逻辑)
# ==================================================================

@router.callback_query(F.data == "notify_change_target")
async def start_change_target(callback: types.CallbackQuery):
    if not await check_vip(callback): return
    await callback.message.delete()
    
    user_id = callback.from_user.id
    
    current_status = "🤖 私聊 (默认)"
    
    async with db.pg_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT notify_target_id, notify_target_name FROM users WHERE tg_id = $1", user_id)
        if row and row['notify_target_id']:
            tid = row['notify_target_id']
            tname = row['notify_target_name'] or "未知群组"
            
            # 🟢 [核心修复] 智能链接生成
            target_link = None
            try:
                # 尝试获取群组详情以拿到 username
                chat_info = await callback.bot.get_chat(tid)
                if chat_info.username:
                    target_link = f"https://t.me/{chat_info.username}"
                elif str(tid).startswith("-100"):
                    # 私有超级群，可用 /c/ 链接
                    clean_id = str(tid).replace("-100", "")
                    target_link = f"https://t.me/c/{clean_id}/1"
                else:
                    # 普通群 (-xxxx)，不支持直接链接，不加链接
                    target_link = None
            except:
                # 获取失败（Bot可能被踢了），尝试用备用逻辑
                if str(tid).startswith("-100"):
                    clean_id = str(tid).replace("-100", "")
                    target_link = f"https://t.me/c/{clean_id}/1"
            
            if target_link:
                current_status = f"<a href='{target_link}'>{tname}</a> (ID: <code>{tid}</code>)"
            else:
                current_status = f"<b>{tname}</b> (ID: <code>{tid}</code>)"

    text = (
        "🎯 <b>更改通知目标设置向导</b>\n\n"
        f"当前绑定：{current_status}\n\n"
        "⚠️ <b>操作说明：</b>\n"
        "1. <b>单群模式</b>：新选择的群组将直接覆盖旧设置。\n"
        "2. <b>权限要求</b>：机器人必须是群管理员，否则发不了消息。\n\n"
        "👇 <b>请点击下方按钮：</b>"
    )
    
    req_btn = KeyboardButton(
        text="📁 选择一个群组", 
        request_chat=KeyboardButtonRequestChat(
            request_id=1, 
            chat_is_channel=False, 
            bot_administrator_rights=None, 
            bot_is_member=False
        )
    )
    
    kb = ReplyKeyboardMarkup(keyboard=[
        [req_btn],
        [KeyboardButton(text="👤 切换回私聊模式")],
        [KeyboardButton(text="🔙 返回上一级")]
    ], resize_keyboard=True, one_time_keyboard=True, input_field_placeholder="请选择群组...")
    
    await callback.message.answer(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)

# ... (on_share_chat, reset_target_text, back_to_panel_text 保持不变) ...
@router.message(F.chat_shared)
async def on_share_chat(message: types.Message):
    chat_id = message.chat_shared.chat_id
    user_id = message.from_user.id
    
    chat_title = "未知群组"
    try:
        chat_info = await message.bot.get_chat(chat_id)
        chat_title = chat_info.title
    except Exception as e:
        chat_title = f"群组({str(chat_id)[-4:]})"
    
    async with db.pg_pool.acquire() as conn:
        await conn.execute("UPDATE users SET notify_target_id = $1, notify_target_name = $2 WHERE tg_id = $3", chat_id, chat_title, user_id)
    
    test_status = "✅ 连接成功，机器人发言正常"
    try:
        await message.bot.send_message(chat_id, f"✅ <b>监听通知服务已连接</b>\n\n操作人：{message.from_user.full_name}\n(本群已设为通知目标)", parse_mode="HTML")
    except Exception:
        test_status = "⚠️ <b>绑定成功，但无法发言！</b>\n请务必将机器人设为【管理员】"

    await message.answer(f"✅ <b>绑定成功！</b>\n\n群组名称：<b>{chat_title}</b>\n检测状态：{test_status}", parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    
    from bot.keyboards import get_reply_main_kb
    kb = await get_reply_main_kb()
    await message.answer("👇 已恢复主菜单", reply_markup=kb)
    await show_notify_panel(message)

@router.message(F.text == "👤 切换回私聊模式")
async def reset_target_text(message: types.Message):
    async with db.pg_pool.acquire() as conn:
        await conn.execute("UPDATE users SET notify_target_id = NULL, notify_target_name = NULL WHERE tg_id = $1", message.from_user.id)
    await message.answer("✅ 已恢复默认：私聊通知", reply_markup=ReplyKeyboardRemove())
    from bot.keyboards import get_reply_main_kb
    kb = await get_reply_main_kb()
    await message.answer("👇", reply_markup=kb)
    await show_notify_panel(message)

@router.message(F.text == "🔙 返回上一级")
async def back_to_panel_text(message: types.Message):
    await message.answer("已取消操作", reply_markup=ReplyKeyboardRemove())
    from bot.keyboards import get_reply_main_kb
    kb = await get_reply_main_kb()
    await message.answer("👇", reply_markup=kb)
    await show_notify_panel(message)

# ==================================================================
# 4. 黑名单管理 (保持不变)
# ==================================================================
@router.callback_query(F.data.startswith("blacklist_view:"))
async def view_blacklist(callback: types.CallbackQuery):
    if not await check_vip(callback): return
    page = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM user_blacklist WHERE user_id = (SELECT id FROM users WHERE tg_id=$1)", user_id)
            total_pages = math.ceil(total / PAGE_SIZE) if total > 0 else 1
            offset = (page - 1) * PAGE_SIZE
            rows = await conn.fetch("SELECT b.id, b.blocked_id, b.blocked_name FROM user_blacklist b JOIN users u ON b.user_id = u.id WHERE u.tg_id = $1 ORDER BY b.id DESC LIMIT $2 OFFSET $3", user_id, PAGE_SIZE, offset)
    kb_rows = []
    for r in rows:
        bid = r['blocked_id']
        bname = r['blocked_name']
        display_label = f"👤 {bname}"
        if bname == "未知用户": display_label = f"👤 ID: {bid}"
        kb_rows.append([InlineKeyboardButton(text=display_label, url=f"tg://user?id={bid}"), InlineKeyboardButton(text="🔓 解封", callback_data=f"blacklist_unban:{r['id']}:{page}")])
    nav = []
    if page > 1: nav.append(InlineKeyboardButton(text="⬅️ 上一页", callback_data=f"blacklist_view:{page-1}"))
    if page < total_pages: nav.append(InlineKeyboardButton(text="下一页 ➡️", callback_data=f"blacklist_view:{page+1}"))
    if nav: kb_rows.append(nav)
    kb_rows.append([InlineKeyboardButton(text="🔙 返回通知控制", callback_data="menu_notify")])
    text = (f"<b>🚫 用户黑名单管理 (第 {page}/{total_pages} 页)</b>\n\n点击左侧按钮可进入其主页，点击 <b>[🔓 解封]</b> 恢复监听。")
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

@router.callback_query(F.data.startswith("blacklist_unban:"))
async def unban_user(callback: types.CallbackQuery):
    _, bid, page = callback.data.split(":")
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            await conn.execute("DELETE FROM user_blacklist WHERE id = $1", int(bid))
    await callback.answer("✅ 已解封")
    await view_blacklist(callback)

@router.callback_query(F.data.startswith("ban_target:"))
async def add_to_blacklist(callback: types.CallbackQuery):
    blocked_tg_id = int(callback.data.split(":")[1])
    user_id = callback.from_user.id
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", user_id)
            if uid:
                await conn.execute("INSERT INTO user_blacklist (user_id, blocked_id, blocked_name) VALUES ($1, $2, '未知用户') ON CONFLICT DO NOTHING", uid, blocked_tg_id)
    await callback.answer("🚫 已拉黑该用户", show_alert=True)