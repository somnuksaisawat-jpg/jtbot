import asyncio
from typing import Union
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from bot.states import DMStates
from core.database import db

router = Router()

# ==================================================================
# 1. 自动私信主面板 (入口)
# ==================================================================
@router.callback_query(F.data == "menu_autodm")
async def show_autodm_panel(event: Union[types.CallbackQuery, types.Message], state: FSMContext = None):
    """显示自动私信控制台"""
    if state: await state.clear()
    
    # 兼容 Message 和 CallbackQuery
    user_id = event.from_user.id
    msg_editor = event.message.edit_text if isinstance(event, types.CallbackQuery) else event.answer

    # 1. 读取数据
    acc_count = 0
    is_running = False
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            # 获取用户DB ID
            uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", user_id)
            if uid:
                # 统计账号
                acc_count = await conn.fetchval("SELECT COUNT(*) FROM dm_accounts WHERE owner_id = $1", uid)
                # 获取开关状态
                is_running = await conn.fetchval("SELECT is_auto_reply FROM dm_settings WHERE user_id = $1", uid)

    # 2. 状态展示
    status_text = "🟢 运行中" if is_running else "🔴 已停止"
    btn_text = "⏸ 暂停任务" if is_running else "▶️ 启动任务"
    btn_callback = "dm_stop" if is_running else "dm_start"

    text = (
        "<b>✈️ 智能私信矩阵控制台</b>\n"
        "------------------------------\n"
        "此功能允许您上传小号，当监听号发现关键词时，\n"
        "<b>自动调用小号</b>去私信发送消息的人。\n\n"
        f"🤖 <b>小号数量：</b>{acc_count} 个\n"
        f"⚙️ <b>任务状态：</b>{status_text}\n"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 管理发送账号", callback_data="dm_acc_list")],
        [InlineKeyboardButton(text="📝 编辑私信话术", callback_data="dm_edit_text")],
        [InlineKeyboardButton(text=btn_text, callback_data=btn_callback)],
        [InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")]
    ])

    try:
        await msg_editor(text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        # 如果编辑失败（比如内容没变），尝试发新消息
        if isinstance(event, types.CallbackQuery):
            await event.message.answer(text, parse_mode="HTML", reply_markup=kb)

# ==================================================================
# 2. 任务开关
# ==================================================================
@router.callback_query(F.data.in_({"dm_start", "dm_stop"}))
async def toggle_dm_task(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    target_status = True if callback.data == "dm_start" else False
    
    async with db.pg_pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", user_id)
        # 确保 settings 存在
        await conn.execute("INSERT INTO dm_settings (user_id) VALUES ($1) ON CONFLICT DO NOTHING", uid)
        # 更新状态
        await conn.execute("UPDATE dm_settings SET is_auto_reply = $1 WHERE user_id = $2", target_status, uid)
        
    await callback.answer("✅ 状态已更新")
    await show_autodm_panel(callback)

# ==================================================================
# 3. 账号管理 (简单列表)
# ==================================================================
@router.callback_query(F.data == "dm_acc_list")
async def show_acc_list(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    
    async with db.pg_pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", user_id)
        rows = await conn.fetch("SELECT phone, status FROM dm_accounts WHERE owner_id = $1 LIMIT 10", uid)
    
    text = "<b>👥 发送账号列表</b>\n\n"
    if not rows:
        text += "暂无账号，请使用 Web 后台上传 Session。"
    else:
        for r in rows:
            text += f"📱 <code>{r['phone']}</code> - {r['status']}\n"
            
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ 添加账号 (Web)", url="http://YOUR_IP:7000/autodm")],
        [InlineKeyboardButton(text="🔙 返回", callback_data="menu_autodm")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

# ==================================================================
# 4. 话术编辑
# ==================================================================
@router.callback_query(F.data == "dm_edit_text")
async def edit_dm_text(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DMStates.editing_content)
    await callback.message.edit_text(
        "📝 <b>请输入新的私信内容：</b>\n(支持文字和链接，暂不支持图片)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 取消", callback_data="menu_autodm")]])
    )

@router.message(DMStates.editing_content)
async def save_dm_text(message: types.Message, state: FSMContext):
    content = message.text
    async with db.pg_pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", message.from_user.id)
        # 停用旧的
        await conn.execute("UPDATE dm_content_templates SET is_active = FALSE WHERE user_id = $1", uid)
        # 插入新的
        await conn.execute("INSERT INTO dm_content_templates (user_id, text_content, is_active) VALUES ($1, $2, TRUE)", uid, content)
        
    await message.answer("✅ 话术已保存！", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 返回控制台", callback_data="menu_autodm")]]))
    await state.clear()