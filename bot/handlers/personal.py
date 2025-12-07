from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from bot.states import ProfileStates
from core.database import db
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from bot.keyboards import get_dynamic_menu # 导入 Inline 菜单生成器

router = Router()

@router.callback_query(F.data == "menu_profile")
async def show_profile(event: types.CallbackQuery):
    """显示个人中心"""
    # 兼容处理：如果是 Message 触发，没有 from_user.id，要在 event 里取
    user_id = event.from_user.id
    
    kw_count = 0
    role_name = "免费用户"
    expire_str = "未开通"
    role_emoji = "🆓"
    
    if db.pg_pool:
        async with db.pg_pool.acquire() as conn:
            user = await conn.fetchrow("SELECT * FROM users WHERE tg_id = $1", user_id)
            if user:
                kw_count = await conn.fetchval("SELECT COUNT(*) FROM keywords WHERE user_id = $1", user['id'])
                if user['role'] == 'vip':
                    role_emoji = "💎"
                    role_name = "高级会员"
                expire_str = str(user['expire_at']) if user['expire_at'] else "未开通"
    
    text = (
        f"<b>{role_emoji} 会员中心 {role_emoji}</b>\n\n"
        f"🆔 用户ID: <code>{user_id}</code>\n"
        f"🎁 会员身份: <b>{role_name}</b>\n"
        f"⏳ 到期时间: {expire_str}\n"
        f"📦 关键词使用: {kw_count} / {'50' if role_name == '高级会员' else '5'}\n\n"
        "👇 点击下方按钮进行充值或管理："
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 购买会员", callback_data="buy_vip")],
        [InlineKeyboardButton(text="💳 卡密激活", callback_data="cdk_redeem")],
        [InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")]
    ])
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "cdk_redeem")
async def start_redeem(callback: types.CallbackQuery, state: FSMContext):
    """点击充值，进入 FSM 状态"""
    await state.set_state(ProfileStates.waiting_for_cdk)
    
    # 临时键盘
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 取消输入")]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )
    
    await callback.message.answer(
        "⌨️ <b>请输入您的充值卡密：</b>\n(例如：VIP-30D-XXXXX)\n\n👇 如不想输入，请点击下方的【取消输入】", 
        parse_mode="HTML",
        reply_markup=kb
    )
    await callback.answer()

@router.message(ProfileStates.waiting_for_cdk)
async def process_cdk(message: types.Message, state: FSMContext):
    """处理输入的卡密"""
    code = message.text.strip()

    # 🟢 [修改] 退出机制优化：恢复主菜单
    if code == "🔙 取消输入" or code.startswith("/") or any(x in code for x in ["⚙️", "🔔", "💎", "💳", "✈️", "🛎"]):
        await state.clear()
        
        # 1. 延迟导入 menu 模块，避免循环引用报错
        from bot.handlers.menu import get_reply_main_kb
        
        # 2. 获取底部常驻键盘
        reply_kb = await get_reply_main_kb()
        
        # 3. 发送消息带上底部键盘
        await message.answer("已退出卡密激活模式。", reply_markup=reply_kb)
        
        # 4. 同时弹出 Inline 功能菜单 (就像发了 /menu 一样)
        await message.answer("👇 请选择下方功能：", reply_markup=await get_dynamic_menu())
        return

    # 检查格式
    if not code.upper().startswith("VIP-"):
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 取消输入")]], resize_keyboard=True)
        await message.answer(
            "❌ <b>格式错误</b>\n卡密应以 <code>VIP-</code> 开头。\n\n请重新输入，或点击下方按钮返回。", 
            parse_mode="HTML",
            reply_markup=kb
        )
        return
    
    # 验证卡密逻辑
    async with db.pg_pool.acquire() as conn:
        cdk = await conn.fetchrow("SELECT * FROM cdks WHERE code = $1 AND status = 'unused'", code)
        
        if not cdk:
            kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔙 取消输入")]], resize_keyboard=True)
            await message.answer("❌ <b>无效的卡密</b>，或者已被使用。\n请检查后重新发送。", parse_mode="HTML", reply_markup=kb)
            return
        
        await conn.execute("UPDATE cdks SET status='used', used_by=(SELECT id FROM users WHERE tg_id=$1), used_at=NOW() WHERE id=$2", message.from_user.id, cdk['id'])
        
        interval = f"{cdk['duration']} {'days' if cdk['unit']=='day' else 'hours'}"
        
        await conn.execute(f"""
            UPDATE users 
            SET role='vip', 
                expire_at = CASE 
                    WHEN expire_at > NOW() THEN expire_at + INTERVAL '{interval}'
                    ELSE NOW() + INTERVAL '{interval}'
                END
            WHERE tg_id = $1
        """, message.from_user.id)
        
    # 充值成功后，也恢复主菜单
    await state.clear()
    from bot.handlers.menu import get_reply_main_kb
    reply_kb = await get_reply_main_kb()
    
    await message.answer(
        f"🎉 <b>充值成功！</b>\n已为您增加 {cdk['duration']} {cdk['unit']} 时长。", 
        parse_mode="HTML", 
        reply_markup=reply_kb # 恢复底部菜单
    )
    # 可选：充值成功后直接显示会员中心
    # await show_profile(message)