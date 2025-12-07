from typing import Union
from aiogram import Router, F, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

async def show_support_panel(event: Union[types.CallbackQuery, types.Message]):
    """显示联系客服面板"""
    
    # ==========================================
    # 🟢 [自定义区域] 在这里修改客服按钮
    # 格式: {"text": "按钮显示的文字", "url": "点击跳转的链接"}
    # 你可以无限复制添加下面的行
    # ==========================================
    my_buttons = [
        {"text": "👨‍💻 24小时在线客服", "url": "https://t.me/avav758"},
        {"text": "💰 商务合作对接",   "url": "https://t.me/rxbot1"},
        {"text": "📢 官方通知频道",   "url": "https://t.me/rxbot1"},
        # {"text": "➕ 这里可以继续加", "url": "https://t.me/xxx"},
    ]
    # ==========================================
    
    # 构建键盘
    kb_rows = []
    
    # 循环添加你定义的按钮 (每行显示 1 个)
    for item in my_buttons:
        kb_rows.append([InlineKeyboardButton(text=item['text'], url=item['url'])])
        
    # 在最后追加返回按钮
    kb_rows.append([InlineKeyboardButton(text="🔙 返回主菜单", callback_data="menu_back")])
    
    text = (
        "<b>🛎 联系客服中心</b>\n\n"
        "如遇充值问题或功能故障，请点击下方按钮联系人工客服。\n"
        "<i>(工作时间：10:00 - 22:00)</i>"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
    
    if isinstance(event, types.CallbackQuery):
        await event.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await event.answer(text, parse_mode="HTML", reply_markup=kb)

# 注册回调
@router.callback_query(F.data == "menu_support")
async def cb_support(callback: types.CallbackQuery):
    await show_support_panel(callback)