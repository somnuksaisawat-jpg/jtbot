import time
import random
import datetime
from typing import Union
from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.database import db
from bot.states import ProfileStates

router = Router()

# ===========================
# 1. 购买会员 - 套餐选择
# ===========================
@router.callback_query(F.data == "buy_vip")
async def show_vip_plans(event: Union[types.CallbackQuery, types.Message]):
    if not db.pg_pool: return
    async with db.pg_pool.acquire() as conn:
        plans = await conn.fetch("SELECT * FROM vip_plans ORDER BY sort_order, id")
    
    kb_rows = []
    if not plans:
        kb_rows.append([InlineKeyboardButton(text="暂无套餐", callback_data="none")])
    else:
        for p in plans:
            kb_rows.append([InlineKeyboardButton(text=f"{p['name']} ({p['price']} U)", callback_data=f"plan_select:{p['id']}:{p['price']}")])
    
    # 卡密激活入口
    kb_rows.append([InlineKeyboardButton(text="💳 卡密激活", callback_data="cdk_redeem"), InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_profile")])
    
    text = "<b>💎 会员充值中心</b>\n\n请选择您需要开通的会员等级："
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows))

# ===========================
# 2. 卡密充值 - 流程闭环 (关键修复)
# ===========================

# 2.1 点击按钮，进入状态
@router.callback_query(F.data == "cdk_redeem")
async def start_redeem(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ProfileStates.waiting_for_cdk)
    # 发送带返回按钮的提示
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 返回", callback_data="buy_vip")]])
    await callback.message.edit_text("⌨️ <b>请输入您的充值卡密：</b>\n(例如：VIP-30D-XXXXX)", parse_mode="HTML", reply_markup=kb)

# 2.2 [新增] 接收输入的卡密文本 (这是之前缺失的！)
@router.message(ProfileStates.waiting_for_cdk)
async def process_cdk(message: types.Message, state: FSMContext):
    code = message.text.strip()
    
    # 简单的格式预检查
    if not code.upper().startswith("VIP-"):
        # 如果用户点的不是卡密而是底部菜单，这里可能会误判，但有了 menu.py 的过滤器，这里通常是安全的
        # 也可以选择忽略非卡密格式
        await message.answer("❌ <b>格式错误</b>\n卡密应以 VIP- 开头。\n请重新输入或点击返回。", parse_mode="HTML")
        return

    async with db.pg_pool.acquire() as conn:
        # 1. 检查卡密有效性
        cdk = await conn.fetchrow("SELECT * FROM cdks WHERE code = $1 AND status = 'unused'", code)
        
        if not cdk:
            await message.answer("❌ <b>无效的卡密</b>\n卡密不存在或已被使用。", parse_mode="HTML")
            return
        
        # 2. 标记已用
        await conn.execute("UPDATE cdks SET status='used', used_by=(SELECT id FROM users WHERE tg_id=$1), used_at=NOW() WHERE id=$2", message.from_user.id, cdk['id'])
        
        # 3. 增加时长
        interval = f"{cdk['duration']} {'days' if cdk['unit']=='day' else 'hours'}"
        
        # 更新用户
        await conn.execute(f"""
            UPDATE users 
            SET role='vip', 
                expire_at = CASE 
                    WHEN expire_at > NOW() THEN expire_at + INTERVAL '{interval}'
                    ELSE NOW() + INTERVAL '{interval}'
                END
            WHERE tg_id = $1
        """, message.from_user.id)
        
    await message.answer(f"🎉 <b>充值成功！</b>\n已为您增加 {cdk['duration']} {cdk['unit']} 时长。", parse_mode="HTML")
    await state.clear()

# ===========================
# 3. 支付流程 (保持不变)
# ===========================
@router.callback_query(F.data.startswith("plan_select:"))
async def select_channel(callback: types.CallbackQuery):
    _, plan_id, price = callback.data.split(":")
    text = f"<b>🛒 订单确认</b>\n\n充值金额: <b>{price} USDT</b>\n\n💡 请选择充值渠道:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="TRC20 (USDT)", callback_data=f"create_order:{plan_id}:TRC20")],
        [InlineKeyboardButton(text="❌ 取消", callback_data="buy_vip")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data.startswith("create_order:"))
async def create_order(callback: types.CallbackQuery):
    try:
        _, plan_id, chain = callback.data.split(":")
        user_id = callback.from_user.id
        async with db.pg_pool.acquire() as conn:
            wallet = await conn.fetchval("SELECT value FROM system_settings WHERE key='usdt_address'")
            if not wallet: return await callback.answer("⚠️ 系统未配置收款地址", show_alert=True)
            plan = await conn.fetchrow("SELECT * FROM vip_plans WHERE id = $1", int(plan_id))
            if not plan: return await callback.answer("⚠️ 套餐不存在", show_alert=True)
            order_no = f"T{int(time.time())}{random.randint(100,999)}"
            pay_amount = float(plan['price'])
            await conn.execute("INSERT INTO orders (order_no, user_id, plan_id, amount, chain, expire_at) VALUES ($1, $2, $3, $4, $5, NOW() + INTERVAL '15 minutes')", order_no, user_id, int(plan_id), pay_amount, chain)
            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={wallet}"
            text = (
                f"<b>💎 订单创建成功！</b>\n请在 <b>15分钟内</b> 完成支付。\n➖➖➖➖➖\n"
                f"💰 <b>支付金额：</b> <code>{pay_amount}</code> USDT\n"
                f"🔗 <b>网络通道：</b> {chain}\n"
                f"wt <b>收款地址：</b> <code>{wallet}</code> (点击复制)\n"
                "➖➖➖➖➖\n⚠️ <b>转账金额必须完全一致！</b>"
            )
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🚫 取消订单", callback_data="cancel_order")]])
            await callback.message.delete()
            await callback.message.answer_photo(photo=qr_url, caption=text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        await callback.answer("❌ 创建失败", show_alert=True)

@router.callback_query(F.data == "cancel_order")
async def cancel_order(callback: types.CallbackQuery):
    await callback.message.delete()
    await callback.answer("✅ 订单已取消！", show_alert=True)